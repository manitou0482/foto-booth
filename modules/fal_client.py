"""Anbindung an die fal.ai API für FLUX.1 [schnell] Image-to-Image.

Der API-Key wird ausschließlich über st.secrets["FAL_KEY"] gelesen
(siehe app.py) und niemals im Code hinterlegt.
"""
import fal_client

# Fest auf 0.75 eingestellt: Gesichter bleiben originalgetreu, während
# Pose/Kleidung/Umgebung stark "morphen". Bewusst kein UI-Regler dafür.
IMAGE_STRENGTH = 0.75
MODEL_ENDPOINT = "fal-ai/flux/schnell/image-to-image"


def generate_image(image_bytes: bytes, prompt: str) -> str:
    """Lädt das Gästefoto zu fal.ai hoch und lässt es per FLUX.1 Schnell
    img2img transformieren. Gibt die URL des Ergebnisbilds zurück."""
    image_url = fal_client.upload(image_bytes, "image/jpeg")

    result = fal_client.run(
        MODEL_ENDPOINT,
        arguments={
            "image_url": image_url,
            "prompt": prompt,
            "strength": IMAGE_STRENGTH,
            "num_inference_steps": 4,
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
