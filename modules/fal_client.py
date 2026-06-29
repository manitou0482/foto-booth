"""Anbindung an die fal.ai API für FLUX.1 Kontext [pro] (bild-editierende Generierung).

Der API-Key wird ausschließlich über st.secrets["FAL_KEY"] gelesen
(siehe app.py) und niemals im Code hinterlegt.

Hinweis zur Modellwahl (empirisch getestet, siehe Konversation):
- Klassisches Image-to-Image (FLUX.1 [dev] image-to-image mit "strength")
  hat keinen Wert, der gleichzeitig (a) das Gesicht erhält UND (b) die Szene
  vollständig verändert - dasselbe Rauschen, das große Kompositionsänderungen
  ermöglicht, verändert zwangsläufig auch das Gesicht.
- PuLID-FLUX (Einzelperson-Identität) löst (a)+(b) für EINE Person gut,
  unterstützt aber keine Gruppenfotos mit mehreren erkennbaren Gesichtern.
- FLUX.1 Kontext [pro] (fal-ai/flux-pro/kontext) bearbeitet das tatsächliche
  Foto per Text-Instruktion, statt die Szene komplett neu zu generieren.
  Dadurch bleiben automatisch ALLE im Originalfoto vorhandenen Gesichter
  erhalten - auch bei 2 Personen (Vater+Kind im Test klar unterscheidbar) -
  UND die Pose wird trotzdem vollständig zum Prompt passend neu erzeugt
  (z.B. sitzend auf einem Dinosaurier statt der ursprünglichen Stehpose).
  Das ist der aktuell verwendete Endpoint.
"""
import io

import fal_client
from PIL import Image

MODEL_ENDPOINT = "fal-ai/flux-pro/kontext"
PERSON_DETECTION_ENDPOINT = "fal-ai/moondream2/object-detection"

GUIDANCE_SCALE = 3.5

# fal.ai verarbeitet das Bild ohnehin in moderater Auflösung - Verkleinerung
# vor dem Upload spart Bandbreite/Zeit (Kontext kostet pauschal $0.04/Bild,
# unabhängig von der Auflösung).
MAX_DIMENSION = 1024


def _resize_for_upload(image_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img.thumbnail((MAX_DIMENSION, MAX_DIMENSION))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _detect_num_people(image_url: str) -> int:
    """Erkennt automatisch, wie viele Personen auf dem Foto sind (Moondream2
    Objekterkennung, ~$0.02/Bild). Bei Fehlern wird konservativ 1 Person
    angenommen, damit die Generierung trotzdem weiterläuft."""
    try:
        result = fal_client.run(
            PERSON_DETECTION_ENDPOINT,
            arguments={"image_url": image_url, "object": "person"},
        )
        count = len(result.get("objects", []))
        return max(count, 1)
    except Exception:
        return 1


def _build_prompt(prompt: str, num_people: int) -> str:
    """Themen-Prompts sind teils in Einzahl ("the person"), teils in Mehrzahl
    ("the people") formuliert - unabhängig von der tatsächlichen Personenzahl
    im Foto. Empirisch getestet: Kontext richtet sich nach der Formulierung
    im Theme-Text, nicht zuverlässig nach dem Originalfoto. Ein generischer,
    vorangestellter Hinweis korrigiert das in beide Richtungen (verhindert
    Klon-Duplikate bei Einzelfotos UND fehlende Personen bei Gruppenfotos) -
    funktioniert für alle 20 Themen gleich, ohne dass die Prompts selbst
    angepasst werden müssen."""
    if num_people <= 1:
        return (
            "There is exactly 1 person in the reference photo. Show only that ONE "
            "person in the new image - do not duplicate them or add extra people. " + prompt
        )
    return (
        f"There are {num_people} people in the reference photo. Include ALL of them "
        f"in the new image, each keeping their own distinct face and identity. " + prompt
    )


def generate_image(image_bytes: bytes, prompt: str) -> str:
    """Lädt das Gästefoto zu fal.ai hoch, erkennt automatisch die Anzahl der
    Personen im Foto und lässt FLUX.1 Kontext daraus ein neues,
    themenpassendes Bild erzeugen, das alle erkannten Gesichter erhält.
    Gibt die URL des Ergebnisbilds zurück."""
    resized_bytes = _resize_for_upload(image_bytes)
    image_url = fal_client.upload(resized_bytes, "image/jpeg")

    num_people = _detect_num_people(image_url)

    result = fal_client.run(
        MODEL_ENDPOINT,
        arguments={
            "prompt": _build_prompt(prompt, num_people),
            "image_url": image_url,
            "guidance_scale": GUIDANCE_SCALE,
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
