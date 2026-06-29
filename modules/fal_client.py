"""Anbindung an die fal.ai API für FLUX.1 [dev] Image-to-Image.

Der API-Key wird ausschließlich über st.secrets["FAL_KEY"] gelesen
(siehe app.py) und niemals im Code hinterlegt.

Hinweis: fal.ai bietet für FLUX.1 [schnell] kein Image-to-Image mit
Prompt+Strength-Steuerung an (nur eine "Redux"-Variante ohne Textprompt und
ohne Strength-Parameter). Für unseren Anwendungsfall (Gesicht erhalten,
Pose/Kleidung/Umgebung per Prompt verändern) brauchen wir daher das
FLUX.1 [dev] Image-to-Image-Modell, das beide Parameter unterstützt.
"""
import io

import fal_client
from PIL import Image

# ACHTUNG: fal.ai definiert "strength" umgekehrt zur klassischen
# Stable-Diffusion-Konvention - laut Doku "controls how much the initial
# image influences the output". Ein HOHER Wert bedeutet hier also NÄHER am
# Originalfoto (weniger Veränderung), nicht mehr Veränderung. Damit der
# Prompt (Dino/Kostüm/Hintergrund) sichtbar greift, aber das Gesicht über
# das Ausgangsbild trotzdem als Anker dient, brauchen wir einen niedrigeren
# Wert als ursprünglich angenommen. Bewusst kein UI-Regler - ggf. hier
# weiter feinjustieren, je nach Testergebnissen.
IMAGE_STRENGTH = 0.35
MODEL_ENDPOINT = "fal-ai/flux/dev/image-to-image"

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
    """Lädt das Gästefoto zu fal.ai hoch und lässt es per FLUX.1 [dev]
    img2img transformieren. Gibt die URL des Ergebnisbilds zurück."""
    resized_bytes = _resize_for_upload(image_bytes)
    image_url = fal_client.upload(resized_bytes, "image/jpeg")

    result = fal_client.run(
        MODEL_ENDPOINT,
        arguments={
            "image_url": image_url,
            "prompt": prompt,
            "strength": IMAGE_STRENGTH,
            "num_inference_steps": 16,
            "enable_safety_checker": True,
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
