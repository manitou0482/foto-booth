"""Anbindung an fal.ai - FLUX.2 Bildgenerierung aus Referenzfoto.

Der API-Key wird ausschließlich über st.secrets["FAL_KEY"] gelesen
(siehe app.py) und niemals im Code hinterlegt.

Pipeline:
1) Foto wird auf fal.ai hochgeladen (als @image1 referenziert).
2) FLUX.2 (SCENE_ENDPOINTS) generiert die themenpassende Szene mit dem
   Referenzfoto - Personenzahl, Posen und Identität werden direkt aus
   @image1 übernommen.
"""
import io
import random

import fal_client
from PIL import Image

SCENE_ENDPOINTS = {
    "dev": "fal-ai/flux-2/edit",       # schnell (~6-7s), für Party-Betrieb
    "pro": "fal-ai/flux-2-pro/edit",   # höhere Qualität, ohne Zeitdruck
}

# fal.ai verarbeitet das Bild ohnehin in moderater Auflösung - Verkleinerung
# vor dem Upload spart Bandbreite/Zeit.
MAX_DIMENSION = 1024


def _resize_for_upload(image_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img.thumbnail((MAX_DIMENSION, MAX_DIMENSION))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


FORMAT_CLAUSE = (
    "The output must be a single cohesive photograph - never a collage, grid, "
    "contact sheet, or multiple separate panels. "
)

FACE_CLAUSE = (
    "Preserve the exact facial features, face shape, skin tone, eye color, hair color "
    "and texture, and overall facial identity of the person from @image1 with maximum "
    "accuracy - their face must be immediately and unmistakably recognizable as the same "
    "individual in the output. Do not alter or genericize the face. "
    "Preserve the gender of the person from @image1 exactly: if the person is a woman, "
    "dress her in the women's version of the themed costume (e.g. period-appropriate "
    "women's dress or feminine variant of the outfit); if the person is a man, dress him "
    "in the men's version. Never change or override the person's gender presentation. "
)


def generate_image(image_bytes: bytes, prompt: str, quality: str = "dev") -> str:
    """Lädt das Foto hoch und lässt FLUX.2 die themenpassende Szene generieren.
    Gibt die URL des generierten Bilds zurück."""
    resized_bytes = _resize_for_upload(image_bytes)
    image_url = fal_client.upload(resized_bytes, "image/jpeg")
    scene_result = fal_client.run(
        SCENE_ENDPOINTS[quality],
        arguments={
            "prompt": FORMAT_CLAUSE + FACE_CLAUSE + prompt,
            "image_urls": [image_url],
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
