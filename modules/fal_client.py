"""4-Schritt Hybrid-Pipeline: FLUX.2 Cloud-Generierung + lokales Face-Blending.

Der API-Key wird ausschließlich über st.secrets["FAL_KEY"] gelesen
(siehe app.py) und niemals im Code hinterlegt.

Pipeline:
1)  Foto hochladen + Ausgabegröße aus Seitenverhältnis berechnen (÷16).
2)  MediaPipe FaceMesh zählt Gesichter lokal → Count-Boostwords an Prompt-Anfang.
    Läuft nur wenn cv2/mediapipe installiert sind (_BLEND_AVAILABLE = True).
3)  FLUX.2 generiert neue Szene aus dem Originalfoto + dynamischem Prompt.
4)  Lokales Face-Blending: Affiner Warp (cv2.getAffineTransform) aus Originalfoto
    + 99×99 Gaussian-Feathering → Gesichter/Haare/Tattoos aus Original erhalten.
    Bei Anzahl-Mismatch (FLUX generiert mehr Personen als Original) werden die
    ersten min(orig, flux) Gesichter geblendet — kein stilles Überspringen mehr.
    Vollständig auf lokaler Festplatte abgeschlossen bevor Schritt 5 startet.
5)  Geblendetes Bild von Festplatte lesen, hochladen → finale URL zurückgeben.
"""
import io
import os
import random
import tempfile

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

# Padding um die erkannte Gesichtsregion (Haar nach oben, Seiten)
_HAIR_PAD_RATIO = 1.0   # 100 % Gesichtshöhe nach oben
_SIDE_PAD_RATIO = 0.35  # 35 % Gesichtsbreite seitlich

# Stabile Ankerpunkte für Affine-Transform:
# 33 = linkes Auge außen, 263 = rechtes Auge außen, 152 = Kinn
_AFFINE_IDX = [33, 263, 152]

# Boostwords je Personenzahl — kommen an den absoluten Prompt-Anfang
# (FLUX gewichtet frühe Tokens stärker → stärkste Count-Unterdrückung)
_COUNT_PREFIXES = {
    1: "1person, solo, alone, single subject, single occupant, ",
    2: "2people, duo, two individuals, side by side, exactly two people, ",
    3: "3people, trio, exactly three people, three individuals, ",
    4: "4people, exactly four people, four individuals, ",
}


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
    """Ausgabegröße passend zum Eingabe-Seitenverhältnis, immer ÷16."""
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
# FaceMesh — Gesichtserkennung + Landmarken
# ---------------------------------------------------------------------------

def _face_mesh_landmarks(image_bgr: np.ndarray, max_faces: int = 4) -> list:
    """Gibt Liste von (468, 2) float32-Arrays zurück (Pixel-Koordinaten je Gesicht),
    sortiert L→R nach Nasenspitze (Landmark 4). Gibt [] zurück wenn keine gefunden."""
    h, w = image_bgr.shape[:2]
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    with mp.solutions.face_mesh.FaceMesh(
        max_num_faces=max_faces,
        refine_landmarks=False,
        min_detection_confidence=0.4,
    ) as fm:
        res = fm.process(rgb)
    if not res.multi_face_landmarks:
        return []
    faces = []
    for fl in res.multi_face_landmarks:
        pts = np.array(
            [(lm.x * w, lm.y * h) for lm in fl.landmark],
            dtype=np.float32,
        )
        faces.append(pts)
    faces.sort(key=lambda pts: pts[4, 0])  # L→R nach Nasenspitze
    return faces


def _count_prefix(n: int) -> str:
    return _COUNT_PREFIXES.get(n, f"{n}people, exactly {n} people, ")


# ---------------------------------------------------------------------------
# Lokales Face-Blending (Affiner Warp + 99×99 Gaussian-Feathering)
# ---------------------------------------------------------------------------

def _blend_faces(
    original_bgr: np.ndarray,
    flux_bgr: np.ndarray,
    orig_lms: list,
) -> np.ndarray:
    """Warpt Originalgesichter + Haare auf die FLUX-Ausgabe via Affin-Transform.

    orig_lms ist gecacht aus Schritt 2 — FaceMesh läuft hier NUR auf flux_bgr.
    Bei Anzahl-Mismatch (FLUX mehr Personen als Original) werden die ersten
    min(orig, flux) Gesichtspaare geblendet (L→R sortiert). Kein stilles
    Überspringen mehr — gibt flux_bgr unverändert nur zurück wenn flux_lms leer."""
    flux_lms = _face_mesh_landmarks(flux_bgr)
    if not flux_lms:
        return flux_bgr

    flux_h, flux_w = flux_bgr.shape[:2]
    result = flux_bgr.copy()

    # Blend so viele Paare wie möglich (L→R sortiert, min von beiden Listen)
    for orig_lm, flux_lm in zip(orig_lms, flux_lms):
        # Affine Transform: 3 stabile Ankerpunkte (Augen außen + Kinn)
        src_pts = orig_lm[_AFFINE_IDX].astype(np.float32)
        dst_pts = flux_lm[_AFFINE_IDX].astype(np.float32)
        M = cv2.getAffineTransform(src_pts, dst_pts)

        # Original-Bild affin auf FLUX-Ausgabegröße warpen
        warped = cv2.warpAffine(
            original_bgr, M, (flux_w, flux_h), flags=cv2.INTER_LANCZOS4
        )

        # Gesichts-Bounding-Box aus FLUX-Landmarken + Haar-/Seiten-Padding
        fx, fy = flux_lm[:, 0], flux_lm[:, 1]
        fw = int(fx.max() - fx.min())
        fh = int(fy.max() - fy.min())
        cx = int((fx.min() + fx.max()) / 2)
        cy = int(fy.min() + fh * 0.35)          # leicht nach oben: Haare einschließen
        rx = fw // 2 + int(fw * _SIDE_PAD_RATIO)
        ry = fh // 2 + int(fh * _HAIR_PAD_RATIO)

        # Ellipsenmaske in Bildgröße + 99×99 Gaussian-Feathering für weiches Blending
        mask = np.zeros((flux_h, flux_w), dtype=np.float32)
        cv2.ellipse(mask, (cx, cy), (rx, ry), 0, 0, 360, 1.0, -1)
        mask = cv2.GaussianBlur(mask, (99, 99), 0)
        mask = mask[:, :, np.newaxis]            # (H, W, 1) für Broadcasting

        # Alpha-Blend: Original-Gesicht × Maske + FLUX × (1 – Maske)
        result = np.clip(
            warped.astype(np.float32) * mask
            + result.astype(np.float32) * (1.0 - mask),
            0, 255,
        ).astype(np.uint8)

    return result


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
    """4-Schritt Hybrid-Pipeline: FLUX.2 generiert Szene, lokales Blending erhält Gesichter."""

    # ── Schritt 1: Upload + Aspect-Ratio-Lock ────────────────────────────────
    resized_bytes = _resize_for_upload(image_bytes)
    image_url = fal_client.upload(resized_bytes, "image/jpeg")
    size = _output_size(image_bytes)

    # ── Schritt 2: Gesichter lokal zählen → Count-Prefix ─────────────────────
    # FaceMesh läuft genau EINMAL auf dem Originalfoto. orig_lms wird gecacht
    # und direkt an _blend_faces() übergeben — kein zweiter Durchlauf in Schritt 4.
    # Wenn _BLEND_AVAILABLE = False (cv2/mediapipe nicht installiert): kein Blending,
    # kein Count-Prefix — FLUX.2 bekommt keinen Personenzahl-Hinweis.
    count_prefix = ""
    orig_lms: list = []
    original_bgr = None
    if _BLEND_AVAILABLE:
        original_bgr = _bytes_to_bgr(resized_bytes)
        orig_lms = _face_mesh_landmarks(original_bgr)
        if orig_lms:
            count_prefix = _count_prefix(len(orig_lms))

    full_prompt = (
        count_prefix          # ← GANZ VORNE: "1person, solo, alone, ..."
        + FORMAT_CLAUSE
        + VISIBILITY_CLAUSE
        + FACE_CLAUSE
        + COUNT_CLAUSE
        + STYLE_CLAUSE
        + prompt
    )

    # ── Schritt 3: FLUX.2 Cloud-Generierung + Download ───────────────────────
    # fal-ai/flux-2/edit hat kein image_guidance_scale — Bildreferenz ist
    # architekturell eingebaut und nicht per Parameter steuerbar.
    scene_result = fal_client.run(
        SCENE_ENDPOINTS[quality],
        arguments={
            "prompt": full_prompt,
            "image_urls": [image_url],
            "image_size": size,
            "seed": random.randint(1, 99999999),
        },
    )
    response = requests.get(scene_result["images"][0]["url"], timeout=30)
    response.raise_for_status()
    flux_bytes = response.content

    # ── Schritt 4: Lokales Face-Blending (vollständig auf Festplatte) ─────────
    # orig_lms aus Schritt 2 gecacht — FaceMesh läuft hier nur noch auf flux_bgr.
    # Bei Anzahl-Mismatch: blend min(orig, flux) Paare statt komplett zu überspringen.
    if _BLEND_AVAILABLE and orig_lms and original_bgr is not None:
        try:
            flux_bgr = _bytes_to_bgr(flux_bytes)
            if original_bgr.shape[:2] != flux_bgr.shape[:2]:
                fh, fw = flux_bgr.shape[:2]
                original_bgr = cv2.resize(
                    original_bgr, (fw, fh), interpolation=cv2.INTER_LANCZOS4
                )
            blended_bgr = _blend_faces(original_bgr, flux_bgr, orig_lms)
            blended_bytes = _bgr_to_bytes(blended_bgr)
        except Exception:
            blended_bytes = flux_bytes
    else:
        blended_bytes = flux_bytes

    # Geblendetes Bild auf lokale Festplatte schreiben.
    # Schritt 5 startet erst wenn tmp.write() vollständig abgeschlossen ist.
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp.write(blended_bytes)
        tmp_path = tmp.name

    # ── Schritt 5: Re-Upload von Festplatte → finale URL ─────────────────────
    try:
        with open(tmp_path, "rb") as f:
            final_url = fal_client.upload(f.read(), "image/jpeg")
    finally:
        os.unlink(tmp_path)  # Temp-Datei aufräumen, auch bei Upload-Fehler

    return final_url
