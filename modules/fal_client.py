"""Anbindung an fal.ai - reiner FLUX.2-Multi-Reference-Aufruf.

Der API-Key wird ausschließlich über st.secrets["FAL_KEY"] gelesen
(siehe app.py) und niemals im Code hinterlegt.

Architektur: FLUX.2 unterstützt Multi-Reference-Editing nativ (Bild als
"@image1" im Prompt referenziert, Identität wird automatisch aus dem
Referenzbild extrahiert). Der frühere Zwei-Schritt-Ansatz (separates
Szene-Modell + fal-ai/face-swap, nötig wegen einer strukturellen Schwäche
von FLUX.1 bei starker Pose-/Verdeckungs-Änderung) ist damit überflüssig.
Zwei Endpoints stehen zur Wahl (siehe SCENE_ENDPOINTS): die schnelle
Dev-Variante für den laufenden Partybetrieb und die Pro-Variante für höhere
Qualität ohne Zeitdruck. Ein zufälliger Seed pro Aufruf sorgt dafür, dass
Pose/Kamerawinkel/Details bei jedem Klick neu ausgewürfelt werden.
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


def generate_image(image_bytes: bytes, prompt: str, quality: str = "dev") -> str:
    """Einziger FLUX.2-Multi-Reference-Aufruf: das Foto wird hochgeladen und
    im Prompt per @image1 referenziert - FLUX.2 extrahiert die Identität
    direkt aus dem Referenzbild, kein separater Face-Swap-Schritt mehr nötig.
    Gibt die URL des generierten Bilds zurück."""
    resized_bytes = _resize_for_upload(image_bytes)
    image_url = fal_client.upload(resized_bytes, "image/jpeg")

    result = fal_client.run(
        SCENE_ENDPOINTS[quality],
        arguments={
            "prompt": prompt,
            "image_urls": [image_url],
            "seed": random.randint(1, 99999999),
        },
    )
    return result["images"][0]["url"]


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
