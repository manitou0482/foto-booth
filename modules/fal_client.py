"""Hybrid-Pipeline: FLUX.2 Cloud-Generierung + lokales Face-Blending.

Der API-Key wird ausschließlich über st.secrets["FAL_KEY"] gelesen
(siehe app.py) und niemals im Code hinterlegt.

Pipeline:
1) Foto hochladen + Ausgabegröße aus Seitenverhältnis berechnen (÷16).
2) FLUX.2 generiert neuen Hintergrund + Kostüm basierend auf @image1.
3) FLUX.2-Ergebnis herunterladen.
4) Lokales Face-Blending: Gesichter + Haare aus Originalfoto per MediaPipe
   extrahieren, auf FLUX.2-Ausgabe warpen und mit weicher Ellipsenmaske einblenden.
5) Geblendetes Bild erneut hochladen → finale URL zurückgeben.
"""
import io
import random

import fal_client
import requests
from PIL import Image

try:
    import cv2
    import mediapipe as mp
    import numpy as np
    _BLEND_AVAILABLE = True
except ImportError:
    _BLEND_AVAILABLE = False

SCENE_ENDPOINTS = {
    "dev": "fal-ai/flux-2/edit",
    "pro": "fal-ai/flux-2-pro/edit",
}

MAX_DIMENSION = 1024

# Padding um erkannte Gesichter für Haar-/Skin-Region
_HAIR_PAD_RATIO = 1.0   # 100 % Gesichtshöhe nach oben (Haare)
_SIDE_PAD_RATIO = 0.35  # 35 % Gesichtsbreite seitlich
_BOT_PAD_RATIO  = 0.10  # 10 % Gesichtshöhe nach unten (Kinn)


# ---------------------------------------------------------------------------
# Bild-Hilfsfunktionen
# ---------------------------------------------------------------------------

def _resize_for_upload(image_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img.thumbnail((MAX_DIMENSION, MAX_DIMENSION))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _output_size(image_bytes: bytes) -> dict:
    """Ausgabegröße passend zum Eingabe-Seitenverhältnis, immer ÷16.
    Verhindert Ghostpersonen durch Kompositions-Neuerfindung bei falschem Ratio."""
    img = Image.open(io.BytesIO(image_bytes))
    w, h = img.size
    if w >= h:
        out_w = MAX_DIMENSION
        out_h = round(h / w * MAX_DIMENSION / 16) * 16
    else:
        out_h = MAX_DIMENSION
        out_w = round(w / h * MAX_DIMENSION / 16) * 16
    return {"width": max(out_w, 16), "height": max(out_h, 16)}


def _bytes_to_bgr(image_bytes: bytes) -> np.ndarray:
    arr = np.frombuffer(image_bytes, np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def _bgr_to_bytes(image_bgr: np.ndarray, quality: int = 90) -> bytes:
    ok, buf = cv2.imencode(".jpg", image_bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("cv2.imencode fehlgeschlagen")
    return buf.tobytes()


# ---------------------------------------------------------------------------
# Gesichtserkennung
# ---------------------------------------------------------------------------

def _detect_faces(image_bgr: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Gibt Liste von (x, y, w, h) für alle erkannten Gesichter zurück,
    sortiert von links nach rechts. Gibt [] zurück wenn keine gefunden."""
    h, w = image_bgr.shape[:2]
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    detector = mp.solutions.face_detection.FaceDetection(
        model_selection=1, min_detection_confidence=0.4
    )
    with detector as det:
        result = det.process(rgb)
    if not result.detections:
        return []
    faces = []
    for det_obj in result.detections:
        bb = det_obj.location_data.relative_bounding_box
        x = max(0, int(bb.xmin * w))
        y = max(0, int(bb.ymin * h))
        fw = min(int(bb.width * w), w - x)
        fh = min(int(bb.height * h), h - y)
        if fw > 10 and fh > 10:
            faces.append((x, y, fw, fh))
    faces.sort(key=lambda f: f[0])
    return faces


# ---------------------------------------------------------------------------
# Weiche Ellipsenmaske
# ---------------------------------------------------------------------------

def _soft_ellipse_mask(height: int, width: int) -> np.ndarray:
    """Float32-Maske (H, W, 1) mit weicher Ellipse, Gaußscher Randunschärfe."""
    mask = np.zeros((height, width), dtype=np.float32)
    cy, cx = height // 2, width // 2
    cv2.ellipse(mask, (cx, cy), (width // 2, height // 2), 0, 0, 360, 1.0, -1)
    blur_r = max(3, min(width, height) // 8)
    if blur_r % 2 == 0:
        blur_r += 1
    mask = cv2.GaussianBlur(mask, (blur_r, blur_r), 0)
    return mask[:, :, np.newaxis]


# ---------------------------------------------------------------------------
# Face-Blending
# ---------------------------------------------------------------------------

def _blend_faces(original_bgr: np.ndarray, flux_bgr: np.ndarray) -> np.ndarray:
    """Extrahiert Gesichter+Haare aus original_bgr, warpt sie auf die
    entsprechenden Gesichtspositionen in flux_bgr und blendet sie ein.
    Graceful fallback: gibt flux_bgr unverändert zurück wenn Erkennung scheitert."""
    orig_h, orig_w = original_bgr.shape[:2]
    flux_h, flux_w = flux_bgr.shape[:2]

    orig_faces = _detect_faces(original_bgr)
    flux_faces = _detect_faces(flux_bgr)

    if not orig_faces or not flux_faces:
        return flux_bgr

    # Gleiche Anzahl Gesichter prüfen – sonst lieber unberührt lassen
    if len(orig_faces) != len(flux_faces):
        return flux_bgr

    result = flux_bgr.copy().astype(np.float32)

    for (ox, oy, ow, oh), (fx, fy, fw, fh) in zip(orig_faces, flux_faces):
        # Region um Gesicht herum (Haare nach oben, Seiten, Kinn)
        hair_pad = int(oh * _HAIR_PAD_RATIO)
        side_pad = int(ow * _SIDE_PAD_RATIO)
        bot_pad  = int(oh * _BOT_PAD_RATIO)

        # Original-Ausschnitt (mit Padding, geclampt auf Bildgrenzen)
        o_x1 = max(0, ox - side_pad)
        o_y1 = max(0, oy - hair_pad)
        o_x2 = min(orig_w, ox + ow + side_pad)
        o_y2 = min(orig_h, oy + oh + bot_pad)
        orig_patch = original_bgr[o_y1:o_y2, o_x1:o_x2]

        # FLUX-Zielregion (gleiche Padding-Verhältnisse, geclampt)
        f_x1 = max(0, fx - int(fw * _SIDE_PAD_RATIO))
        f_y1 = max(0, fy - int(fh * _HAIR_PAD_RATIO))
        f_x2 = min(flux_w, fx + fw + int(fw * _SIDE_PAD_RATIO))
        f_y2 = min(flux_h, fy + fh + int(fh * _BOT_PAD_RATIO))

        target_w = f_x2 - f_x1
        target_h = f_y2 - f_y1

        if target_w < 4 or target_h < 4 or orig_patch.size == 0:
            continue

        # Patch auf Zielgröße skalieren
        warped = cv2.resize(orig_patch, (target_w, target_h), interpolation=cv2.INTER_LANCZOS4)

        # Weiche Ellipsenmaske
        mask = _soft_ellipse_mask(target_h, target_w)  # float32 (H,W,1)

        flux_region = result[f_y1:f_y2, f_x1:f_x2].astype(np.float32)
        warped_f    = warped.astype(np.float32)
        blended     = warped_f * mask + flux_region * (1.0 - mask)
        result[f_y1:f_y2, f_x1:f_x2] = blended

    return np.clip(result, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------------------
# Prompt-Bausteine
# ---------------------------------------------------------------------------

FORMAT_CLAUSE = (
    "The output must be a single cohesive photograph - never a collage, grid, "
    "contact sheet, or multiple separate panels. "
)

FACE_CLAUSE = (
    "Preserve the exact facial features, face shape, skin tone, eye color, hair color "
    "and texture of every person with maximum accuracy - each person must remain "
    "immediately recognizable as themselves. "
    "Preserve gender exactly from @image1: dress women in women's costume variants, men in men's. "
)

COUNT_CLAUSE = (
    "CRITICAL — person count: The output must contain EXACTLY the same number of people "
    "as the foreground subjects in @image1 — not one more, not one less. "
    "Count the foreground people in @image1 carefully and reproduce that exact number. "
    "Ignore all background people in @image1. Do not invent additional characters. "
)

VISIBILITY_CLAUSE = (
    "Every person's face must stay fully visible and unobstructed — no helmets, masks, "
    "full-face visors, or hoods covering any part of the face, even if the costume would "
    "normally include one. "
)

STYLE_CLAUSE = (
    "The result should look like a fun, memorable photobooth photo — clear and easy to "
    "read at a glance, not an overwhelming epic movie poster. Keep the background "
    "simple and uncluttered. Good natural lighting, no extreme dramatic effects. "
)


# ---------------------------------------------------------------------------
# Haupt-Generierungsfunktion
# ---------------------------------------------------------------------------

def generate_image(image_bytes: bytes, prompt: str, quality: str = "dev") -> str:
    """Hybrid-Pipeline: FLUX.2 generiert Szene, lokales Blending erhält Gesichter."""
    # 1. Hochladen + Aspect-Ratio-Lock
    resized_bytes = _resize_for_upload(image_bytes)
    image_url = fal_client.upload(resized_bytes, "image/jpeg")
    size = _output_size(image_bytes)

    # 2. FLUX.2 Cloud-Generierung
    full_prompt = (
        FORMAT_CLAUSE
        + VISIBILITY_CLAUSE
        + FACE_CLAUSE
        + COUNT_CLAUSE
        + STYLE_CLAUSE
        + prompt
    )
    scene_result = fal_client.run(
        SCENE_ENDPOINTS[quality],
        arguments={
            "prompt": full_prompt,
            "image_urls": [image_url],
            "image_size": size,
            "seed": random.randint(1, 99999999),
        },
    )
    flux_url = scene_result["images"][0]["url"]

    # 3. FLUX-Ergebnis herunterladen
    response = requests.get(flux_url, timeout=30)
    response.raise_for_status()
    flux_bytes = response.content

    # 4. Lokales Face-Blending (nur wenn cv2/mediapipe verfügbar)
    if _BLEND_AVAILABLE:
        try:
            original_bgr = _bytes_to_bgr(resized_bytes)
            flux_bgr     = _bytes_to_bgr(flux_bytes)

            # Auf gleiche Größe bringen falls nötig
            if original_bgr.shape[:2] != flux_bgr.shape[:2]:
                flux_h, flux_w = flux_bgr.shape[:2]
                original_bgr = cv2.resize(original_bgr, (flux_w, flux_h), interpolation=cv2.INTER_LANCZOS4)

            blended_bgr   = _blend_faces(original_bgr, flux_bgr)
            blended_bytes = _bgr_to_bytes(blended_bgr)
        except Exception:
            blended_bytes = flux_bytes
    else:
        blended_bytes = flux_bytes

    # 5. Geblendetes Bild hochladen + URL zurückgeben
    final_url = fal_client.upload(blended_bytes, "image/jpeg")
    return final_url
