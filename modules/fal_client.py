"""Anbindung an fal.ai - FLUX.2-Multi-Reference-Szene + Face-Swap.

Der API-Key wird ausschließlich über st.secrets["FAL_KEY"] gelesen
(siehe app.py) und niemals im Code hinterlegt.

Architektur: FLUX.2 unterstützt Multi-Reference-Editing nativ (Bild als
"@image1" im Prompt referenziert), ABER ein Live-Test mit echten Gästefotos
hat erneut die schon einmal nachgewiesene strukturelle Schwäche gezeigt: bei
dramatischer Pose-/Kostüm-Änderung (volle Ritterrüstung, Helm, Verdeckung)
"vergisst" das Modell zuverlässig das Originalgesicht - selbst bei einem
Solo-Foto. Deshalb läuft die Identität wieder über einen zweiten, dedizierten
Schritt:
1) FLUX.2 (SCENE_ENDPOINTS) erzeugt Szene/Pose/Kleidung/Hintergrund mit
   voller kreativer Freiheit aus dem Referenzfoto.
2) fal-ai/face-swap setzt danach das ECHTE Gesicht aus dem Originalfoto auf
   das generierte Bild - empirisch bestätigt auch bei mehreren Personen im
   Foto (Gesichter werden positionsweise zugeordnet).
Die Personenzahl wird automatisch erkannt (Moondream2), damit FLUX.2 auch
bei Gruppenfotos die richtige Anzahl Personen in die Szene zeichnet (die
Themen-Prompts sind alle in der Einzahl formuliert).
"""
import io
import random
import re

import fal_client
from PIL import Image

SCENE_ENDPOINTS = {
    "dev": "fal-ai/flux-2/edit",       # schnell (~6-7s), für Party-Betrieb
    "pro": "fal-ai/flux-2-pro/edit",   # höhere Qualität, ohne Zeitdruck
}
FACE_SWAP_ENDPOINT = "fal-ai/face-swap"
PERSON_DETECTION_ENDPOINT = "fal-ai/moondream2/object-detection"

# fal.ai verarbeitet das Bild ohnehin in moderater Auflösung - Verkleinerung
# vor dem Upload spart Bandbreite/Zeit.
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


def _pluralize(prompt: str) -> str:
    """Alle 20 Themen-Prompts sind einheitlich in der Einzahl formuliert
    ("the person from @image1..."). Bei mehreren Personen im Foto wird der
    Wortlaut direkt im Prompt-Text auf Mehrzahl umgestellt, statt für jedes
    Thema eine eigene Mehrzahl-Variante zu pflegen."""
    prompt = prompt.replace("the person from @image1", "the people from @image1")
    prompt = prompt.replace("The person ", "The people ")
    prompt = re.sub(r"\binteracts\b", "interact", prompt)
    prompt = re.sub(r"\bkeeps their expression\b", "keep their expressions", prompt)
    return prompt


FORMAT_CLAUSE = (
    "The output must be a single cohesive photograph - never a collage, grid, "
    "contact sheet, or multiple separate panels. "
)


def _build_prompt(prompt: str, num_people: int) -> str:
    if num_people <= 1:
        count_clause = (
            "There is exactly 1 person in the reference photo @image1. Show only that "
            "ONE person in the new image - do not duplicate them or add extra people. "
        )
    else:
        prompt = _pluralize(prompt)
        count_clause = (
            f"There are {num_people} people in the reference photo @image1, together in "
            f"one shared scene. Include ALL of them in the new image, each keeping their "
            f"own actual apparent age and gender from the reference photo (e.g. a child "
            f"must stay a child, not become an adult) - do not duplicate any of them or "
            f"add extra people. "
        )
    return FORMAT_CLAUSE + count_clause + prompt


def generate_image(
    image_bytes: bytes,
    prompt: str,
    quality: str = "dev",
    group_mode: bool = False,
) -> str:
    """FLUX.2-Pipeline. Im dev-Modus (Party): nur Upload + Szene = 2 API-Calls.
    Im pro-Modus: zusätzlich face-swap für maximale Gesichts-Treue.
    group_mode=True aktiviert Moondream2-Personenerkennung für Gruppenfotos."""
    resized_bytes = _resize_for_upload(image_bytes)
    image_url = fal_client.upload(resized_bytes, "image/jpeg")

    num_people = _detect_num_people(image_url) if group_mode else 1

    scene_result = fal_client.run(
        SCENE_ENDPOINTS[quality],
        arguments={
            "prompt": _build_prompt(prompt, num_people),
            "image_urls": [image_url],
            "seed": random.randint(1, 99999999),
        },
    )
    scene_url = scene_result["images"][0]["url"]

    if quality == "pro":
        swap_result = fal_client.run(
            FACE_SWAP_ENDPOINT,
            arguments={"base_image_url": scene_url, "swap_image_url": image_url},
        )
        return swap_result["image"]["url"]

    return scene_url


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
