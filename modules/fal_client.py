"""Anbindung an fal.ai - Zwei-Schritt-Pipeline: Szene generieren + Gesicht tauschen.

Der API-Key wird ausschließlich über st.secrets["FAL_KEY"] gelesen
(siehe app.py) und niemals im Code hinterlegt.

Hinweis zur Architektur (empirisch nach intensivem Live-Testen mit echten
Gästefotos ermittelt, siehe Konversation):
- Ein einzelner Aufruf an FLUX.1 Kontext [pro] mit der Anweisung "behalte das
  Gesicht UND ändere Pose/Kleidung/Hintergrund radikal" funktioniert NUR bei
  Themen, die nah an der Originalkomposition bleiben (z.B. Pirat, Cyberpunk -
  Person bleibt stehend, Gesicht frei sichtbar). Bei Themen mit starker
  Verdeckung (Astronaut-Helm) oder dramatischer Pose-Änderung (Dino-Ritt)
  "vergisst" das Modell das Originalgesicht zuverlässig - das ist eine
  strukturelle Grenze, kein Prompt-Problem, und kein Gewichts-Wert behebt das.
- Lösung: Pose-Generierung und Gesichts-Identität werden in zwei
  unabhängige Schritte aufgeteilt (vermutlich macht Touchpix das ähnlich):
  1) FLUX.1 Kontext [pro] erzeugt die Szene (Pose, Kleidung, Hintergrund)
     mit voller kreativer Freiheit - OHNE Identitäts-Zwang, der die Pose
     ohnehin nur einschränkt, ohne zuverlässig zu wirken.
  2) fal-ai/face-swap setzt das ECHTE Gesicht aus dem Originalfoto auf das
     generierte Bild. Face-Swap-Modelle sind speziell darauf trainiert,
     ein Gesicht auf eine andere Kopf-/Körperhaltung zu übertragen - das ist
     robuster als Identität "by prompt" zu erzwingen. Ein einzelner Aufruf
     mit dem ganzen Gruppenfoto als Quelle und Ziel tauscht dabei empirisch
     bestätigt auch bei 2 Personen beide Gesichter korrekt positionsweise.
"""
import io
import random

import fal_client
from PIL import Image

SCENE_MODEL_ENDPOINT = "fal-ai/flux-pro/kontext"
FACE_SWAP_ENDPOINT = "fal-ai/face-swap"
PERSON_DETECTION_ENDPOINT = "fal-ai/moondream2/object-detection"

GUIDANCE_SCALE = 3.5

# Themen-Prompts können den Platzhalter {ACTION} enthalten, der bei jeder
# Generierung durch eine zufällig gewählte, zum Thema passende Pose/Aktion
# ersetzt wird - damit nicht immer dieselbe Geste/Haltung entsteht (z.B.
# "winkt immer" beim Dino-Thema, "steht immer nur" beim Piraten-Thema).
# Pop-Art-Comic und Anime-Hero haben bewusst KEINEN Pool, da sie laut
# eigenem Prompt-Text die Original-Pose/den Original-Ausdruck 1:1 erhalten
# sollen (Stil-Transfer statt Pose-Änderung).
ACTION_POOLS = {
    "dino_ritt": [
        "laughing and waving directly at the camera",
        "shouting triumphantly with one fist raised in the air",
        "pointing excitedly ahead",
        "holding on tight while looking back over their shoulder with a thrilled grin",
        "cheering with both arms raised in excitement",
        "gasping in playful surprise with wide eyes and an open-mouthed smile",
        "giving a confident thumbs up",
    ],
    "astronaut": [
        "waving joyfully at the camera",
        "giving an excited thumbs up while floating",
        "reaching playfully toward the Earth reflection in the visor",
        "laughing while floating weightlessly with arms spread wide",
        "doing a playful zero-gravity somersault",
    ],
    "cyberpunk": [
        "standing confidently and looking straight at the camera",
        "leaning back against a neon-lit wall with arms crossed",
        "walking forward with a determined stride",
        "looking back over one shoulder with a sharp smirk",
        "adjusting their jacket collar confidently",
    ],
    "medieval_knight": [
        "facing the camera with a confident, proud smile",
        "kneeling with their sword planted in the ground",
        "raising their sword triumphantly overhead",
        "standing guard with a shield raised",
        "saluting with a fist over their chest",
    ],
    "pirate_captain": [
        "grinning confidently directly at the camera, wind blowing through their hair",
        "hanging playfully from the ship's rigging",
        "fighting boldly at the ship's cannon",
        "standing with one boot triumphantly on a treasure chest",
        "raising a cutlass triumphantly on the deck",
    ],
    "wild_west_sheriff": [
        "standing confidently with a determined expression",
        "drawing their revolver in a quick-draw stance",
        "leaning casually against a saloon post",
        "tipping their hat with a sly smirk",
        "standing in a tense duel-ready stance",
    ],
    "viking_warrior": [
        "standing powerful and proud, looking directly at the camera",
        "raising a battle axe triumphantly overhead",
        "letting out a fierce battle cry",
        "blowing a war horn",
        "kneeling and planting their axe into the ground",
    ],
    "superhero": [
        "standing in a heroic pose, looking confidently at the camera",
        "flying forward with their cape billowing behind them",
        "landing in a dramatic heroic crouch",
        "punching the air triumphantly",
        "standing protectively with arms crossed",
    ],
    "mermaid_underwater": [
        "expression joyful and serene, looking toward the camera",
        "twirling gracefully through the water",
        "reaching playfully toward a school of colorful fish",
        "resting elegantly on a coral reef",
        "swimming gracefully upward toward the light above",
    ],
    "renaissance_royalty": [
        "sitting with regal, composed posture, looking elegantly at the camera",
        "raising a golden goblet in an elegant toast",
        "gesturing gracefully with one hand",
        "standing regally beside an ornate throne",
        "looking thoughtfully out of a tall palace window",
    ],
    "gatsby_1920s": [
        "posing confidently with a charming smile",
        "dancing playfully with a glass of champagne in hand",
        "laughing joyfully amid drifting confetti",
        "leaning charismatically against a grand piano",
        "striking a glamorous pose amid the party",
    ],
    "safari_adventure": [
        "looking excited and adventurous directly at the camera",
        "pointing excitedly toward distant wildlife",
        "crouching low while observing through binoculars",
        "climbing triumphantly onto a fallen log",
        "laughing while holding a field journal",
    ],
    "winter_wonderland_santa": [
        "smiling warmly and waving at the camera",
        "laughing while holding a beautifully wrapped gift",
        "sitting cozily beside a decorated Christmas tree",
        "throwing a playful snowball",
        "hugging a wrapped present joyfully",
    ],
    "tropical_beach_paradise": [
        "smiling happily directly at the camera",
        "relaxing playfully in a beachside hammock",
        "splashing joyfully in the shallow turquoise water",
        "walking barefoot along the shoreline",
        "raising a tropical cocktail cheerfully",
    ],
    "disco_70s": [
        "striking a confident, fun dance pose",
        "spinning playfully under the glowing disco lights",
        "pointing confidently toward the sky mid-dance",
        "laughing joyfully amid the dance floor lights",
        "striking a glamorous disco pose with arms raised",
    ],
    "scifi_mech_pilot": [
        "looking determined and confident directly at the camera",
        "giving a confident thumbs up from the cockpit",
        "operating the holographic controls intently",
        "saluting confidently before launch",
        "leaning out of the cockpit with a determined grin",
    ],
    "fairy_tale_forest": [
        "smiling softly, looking gently enchanted toward the camera",
        "twirling playfully amid floating magical lights",
        "reaching out gently toward a glowing firefly",
        "sitting peacefully upon a mossy log",
        "dancing gracefully among the ancient trees",
    ],
    "egyptian_pharaoh": [
        "holding a regal, powerful pose, looking directly at the camera",
        "raising a golden staff triumphantly",
        "sitting regally upon an ornate throne",
        "gesturing commandingly with one outstretched arm",
        "standing proudly between towering temple columns",
    ],
}


def _randomize_action(theme_id: str, prompt: str) -> str:
    if "{ACTION}" not in prompt:
        return prompt
    pool = ACTION_POOLS.get(theme_id, ["standing confidently, looking directly at the camera"])
    return prompt.replace("{ACTION}", random.choice(pool))

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
    im Foto. Die Einzahl/Mehrzahl-Formulierung wird direkt im Prompt-Text
    selbst ausgetauscht (zusätzlich zum Hinweissatz) - funktioniert für alle
    20 Themen gleich, ohne dass die Prompts selbst manuell angepasst werden
    müssen. Kein Identitäts-Hinweis mehr nötig: Das Gesicht wird nicht mehr
    von diesem Schritt erzeugt, sondern in Schritt 2 (Face-Swap) ersetzt -
    dieser Schritt darf sich daher voll auf Pose/Kleidung/Hintergrund
    konzentrieren, ohne durch einen Identitäts-Zwang eingeschränkt zu sein."""
    if num_people <= 1:
        prompt = prompt.replace("The people from the photo", "The person from the photo")
        count_clause = (
            "There is exactly 1 person in the reference photo. Show only that ONE "
            "person in the new image - do not duplicate them or add extra people. "
        )
    else:
        prompt = prompt.replace("The person from the photo", "The people from the photo")
        count_clause = (
            f"There are {num_people} people in the reference photo. Include ALL of them "
            f"in the new image, each in their own distinct pose. "
        )

    # Kleidung soll zum jeweiligen Geschlecht passen statt einer festen
    # (oft männlich wirkenden) Standardvariante.
    gender_clause = (
        "Style all clothing and costume details to naturally match each person's own "
        "apparent gender presentation from the reference photo. "
    )
    return gender_clause + count_clause + prompt


def generate_image(image_bytes: bytes, prompt: str, theme_id: str) -> str:
    """Zwei-Schritt-Pipeline:
    1) FLUX.1 Kontext erzeugt die themenpassende Szene (Pose/Kleidung/
       Hintergrund) mit voller kreativer Freiheit aus dem Gästefoto.
    2) fal-ai/face-swap setzt das echte Gesicht aus dem Originalfoto auf
       das generierte Bild - das macht die Gesichts-Identität unabhängig
       davon, wie dramatisch die Pose/Verdeckung im jeweiligen Thema ist.
    Gibt die URL des finalen Ergebnisbilds zurück."""
    resized_bytes = _resize_for_upload(image_bytes)
    image_url = fal_client.upload(resized_bytes, "image/jpeg")

    num_people = _detect_num_people(image_url)
    prompt = _randomize_action(theme_id, prompt)

    scene_result = fal_client.run(
        SCENE_MODEL_ENDPOINT,
        arguments={
            "prompt": _build_prompt(prompt, num_people),
            "image_url": image_url,
            "guidance_scale": GUIDANCE_SCALE,
        },
    )
    scene_url = scene_result["images"][0]["url"]

    swap_result = fal_client.run(
        FACE_SWAP_ENDPOINT,
        arguments={"base_image_url": scene_url, "swap_image_url": image_url},
    )
    return swap_result["image"]["url"]


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
