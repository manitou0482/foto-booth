"""Anbindung an die fal.ai API für PuLID-FLUX (gesichtserhaltende Generierung).

Der API-Key wird ausschließlich über st.secrets["FAL_KEY"] gelesen
(siehe app.py) und niemals im Code hinterlegt.

Hinweis zur Modellwahl: Klassisches Image-to-Image (FLUX.1 [dev]
image-to-image mit "strength") wurde getestet und konnte keinen Wert finden,
der gleichzeitig (a) das Gesicht erkennbar erhält UND (b) die Szene
vollständig verändert (Dino/Kostüm/Hintergrund) - dasselbe Diffusions-
"Rauschen", das große Szenenänderungen ermöglicht, verändert zwangsläufig
auch das Gesicht. PuLID-FLUX (fal-ai/flux-pulid) ist speziell für genau
dieses Problem gebaut: Es nimmt ein Referenzfoto der Person UND einen
Text-Prompt entgegen und erzeugt ein komplett neues Bild, in dem die
Gesichts-Identität separat eingebettet erhalten bleibt (vergleichbar mit
dem, was Touchpix vermutlich einsetzt).
"""
import io

import fal_client
from PIL import Image

MODEL_ENDPOINT = "fal-ai/flux-pulid"

# Wie stark die Gesichts-Identität erhalten bleiben soll (0-1, fal.ai-Default
# ist 1 = maximale Identitätstreue). Bewusst kein UI-Regler dafür.
ID_WEIGHT = 1.0

NEGATIVE_PROMPT = "blurry, distorted, deformed face, extra limbs, low quality, watermark"

# fal.ai berechnet pro Megapixel des Bildes - wir verkleinern daher vor dem
# Upload, um Kosten und Verarbeitungszeit vorhersehbar klein zu halten.
MAX_DIMENSION = 1024


def _resize_for_upload(image_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img.thumbnail((MAX_DIMENSION, MAX_DIMENSION))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def generate_image(image_bytes: bytes, prompt: str) -> str:
    """Lädt das Gästefoto zu fal.ai hoch und lässt PuLID-FLUX daraus ein
    neues, themenpassendes Bild erzeugen, das die Gesichts-Identität
    erhält. Gibt die URL des Ergebnisbilds zurück."""
    resized_bytes = _resize_for_upload(image_bytes)
    reference_image_url = fal_client.upload(resized_bytes, "image/jpeg")

    result = fal_client.run(
        MODEL_ENDPOINT,
        arguments={
            "prompt": prompt,
            "reference_image_url": reference_image_url,
            "id_weight": ID_WEIGHT,
            "negative_prompt": NEGATIVE_PROMPT,
            "guidance_scale": 4,
            "num_inference_steps": 20,
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
