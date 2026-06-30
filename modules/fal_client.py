"""Anbindung an fal.ai - FLUX Img2Img Bildgenerierung aus Referenzfoto.

Der API-Key wird ausschließlich über st.secrets["FAL_KEY"] gelesen
(siehe app.py) und niemals im Code hinterlegt.

Pipeline:
1) Foto wird auf fal.ai hochgeladen.
2) Ausgabegröße wird aus dem Seitenverhältnis des Originalfotos berechnet
   (durch 16 teilbar) - verhindert Ghostpersonen durch Kompositions-Neuerfindung.
3) FLUX Img2Img transformiert das Foto mit GENERATION_STRENGTH: Personen-
   Positionen bleiben strukturell erhalten, Hintergrund und Kleidung ändern sich.
"""
import io
import random

import fal_client
from PIL import Image

SCENE_ENDPOINTS = {
    "dev": "fal-ai/flux/dev/image-to-image",
    "pro": "fal-ai/flux-pro/image-to-image",
}

# Stärke der Transformation (0 = unverändertes Original, 1 = komplett neu).
# 0.70: Personen-Positionen strukturell erhalten, Hintergrund/Kleidung ändern sich.
# Niedriger = weniger Ghostpersonen, aber weniger dramatische Szene.
# Höher = kreativere Szene, aber mehr Risiko für Ghostpersonen.
GENERATION_STRENGTH = 0.70

MAX_DIMENSION = 1024


def _resize_for_upload(image_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img.thumbnail((MAX_DIMENSION, MAX_DIMENSION))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _output_size(image_bytes: bytes) -> dict:
    """Berechnet Ausgabegröße passend zum Eingabe-Seitenverhältnis, immer
    durch 16 teilbar. Ein abweichendes Seitenverhältnis zwingt FLUX die
    Komposition neu zu erfinden - Hauptursache für Ghostpersonen."""
    img = Image.open(io.BytesIO(image_bytes))
    w, h = img.size
    if w >= h:
        out_w = MAX_DIMENSION
        out_h = round(h / w * MAX_DIMENSION / 16) * 16
    else:
        out_h = MAX_DIMENSION
        out_w = round(w / h * MAX_DIMENSION / 16) * 16
    return {"width": max(out_w, 16), "height": max(out_h, 16)}


FORMAT_CLAUSE = (
    "The output must be a single cohesive photograph - never a collage, grid, "
    "contact sheet, or multiple separate panels. "
)

FACE_CLAUSE = (
    "Preserve the exact facial features, face shape, skin tone, eye color, hair color "
    "and texture of every person with maximum accuracy - each person must remain "
    "immediately recognizable as themselves. "
    "Preserve gender exactly: dress women in women's costume variants, men in men's. "
)

COUNT_CLAUSE = (
    "Include only the people who are clearly in the foreground and facing the camera. "
    "Do not add extra people or background bystanders. "
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


def generate_image(image_bytes: bytes, prompt: str, quality: str = "dev") -> str:
    """Lädt das Foto hoch und transformiert es per FLUX Img2Img in die
    themenpassende Szene. Gibt die URL des generierten Bilds zurück."""
    resized_bytes = _resize_for_upload(image_bytes)
    image_url = fal_client.upload(resized_bytes, "image/jpeg")
    size = _output_size(image_bytes)
    scene_result = fal_client.run(
        SCENE_ENDPOINTS[quality],
        arguments={
            "prompt": FORMAT_CLAUSE + VISIBILITY_CLAUSE + FACE_CLAUSE + COUNT_CLAUSE + STYLE_CLAUSE + prompt,
            "image_url": image_url,
            "strength": GENERATION_STRENGTH,
            "image_size": size,
            "seed": random.randint(1, 99999999),
        },
    )
    return scene_result["images"][0]["url"]


# ---------------------------------------------------------------------------
# TODO / Platzhalter für eine künftige lokale Druck-Bridge.
#
# Streamlit Community Cloud läuft in der Cloud und hat KEINEN Zugriff auf
# den Canon Selphy CP1200 im lokalen WLAN. Diese Funktion ist daher bewusst
# nicht implementiert und wird nirgendwo aufgerufen oder importiert
# (keine win32print/cups-Abhängigkeit im Cloud-Code!).
#
# Geplanter Ansatz: ein separates Python-Skript läuft auf einem PC/Laptop
# im selben WLAN wie der Drucker, pollt periodisch die neuesten
# result_image_url-Werte (z.B. über eine kleine geteilte Liste/Queue) und
# druckt sie lokal via win32print (Windows) oder CUPS (Linux/Mac).
#
# def trigger_background_print(image_url: str):
#     pass
# ---------------------------------------------------------------------------
