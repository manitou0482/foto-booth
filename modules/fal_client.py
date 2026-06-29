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
  1) Ein Edit-Modell erzeugt die Szene (Pose, Kleidung, Hintergrund) mit
     voller kreativer Freiheit - OHNE Identitäts-Zwang, der die Pose ohnehin
     nur einschränkt, ohne zuverlässig zu wirken.
  2) fal-ai/face-swap setzt das ECHTE Gesicht aus dem Originalfoto auf das
     generierte Bild. Face-Swap-Modelle sind speziell darauf trainiert,
     ein Gesicht auf eine andere Kopf-/Körperhaltung zu übertragen - das ist
     robuster als Identität "by prompt" zu erzwingen. Ein einzelner Aufruf
     mit dem ganzen Gruppenfoto als Quelle und Ziel tauscht dabei empirisch
     bestätigt auch bei 2 Personen beide Gesichter korrekt positionsweise.
- Geschwindigkeit (empirisch verglichen): `fal-ai/flux-2/edit` erzeugt die
  Szene in ca. 6-7s (8 Inferenzschritte), `fal-ai/flux-pro/kontext` braucht
  ca. 15s (50 Schritte) bei vergleichbarer Qualität - deshalb aktuell im
  Einsatz. Eine zusätzlich getestete Variante mit zwei Civitai-LoRAs über
  `fal-ai/flux-general` (Text-zu-Bild ohne Foto-Input) war mit 24-31s sogar
  LANGSAMER (vermutlich durch das Laden der ~300MB-LoRA-Dateien) und nicht
  erkennbar besser in der Qualität - deshalb nicht übernommen. Der größte
  verbleibende Zeitfaktor ist inzwischen der Face-Swap-Schritt selbst
  (variabel 3-30s je nach Auslastung), der bisher nicht weiter optimiert ist.
"""
import io
import random

import fal_client
from PIL import Image

SCENE_MODEL_ENDPOINT = "fal-ai/flux-2/edit"
FACE_SWAP_ENDPOINT = "fal-ai/face-swap"
PERSON_DETECTION_ENDPOINT = "fal-ai/moondream2/object-detection"

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


# Zusätzlich zu {ACTION} können Theme-Prompts {CLOTHING}, {BACKGROUND} und
# {PROP} enthalten - sonst blieben Kleidung/Schauplatz/Requisite bei jeder
# Generierung exakt gleich, auch wenn sich die Pose änderte ("immer derselbe
# Astronaut/Sheriff"). Jeweils 3 thema-passende Varianten pro Thema.
CLOTHING_POOLS = {
    "dino_ritt": [
        "vintage explorer clothing, safari shirts, and khaki adventure gear",
        "a rugged leather jacket with explorer satchels and tall boots",
        "a worn denim survivalist outfit with a wide-brim hat",
    ],
    "astronaut": [
        "a classic NASA astronaut spacesuit",
        "an extravehicular activity (EVA) spacesuit with a tethered safety line",
        "a lightweight in-flight jumpsuit with NASA patches",
    ],
    "cyberpunk": [
        "a high-tech dark leather jacket with glowing cyan and magenta LED fiber optics",
        "a sleek holographic-trim trench coat with neon piping",
        "an armored streetwear vest with glowing circuit patterns",
    ],
    "medieval_knight": [
        "detailed, polished steel plate armor with intricate engravings",
        "chainmail armor with a heraldic tabard",
        "ceremonial gilded armor with a flowing cape",
    ],
    "pirate_captain": [
        "a weathered tricorn hat, an ornate captain's coat, a ruffled shirt, and a leather belt",
        "a rugged bandana, a patched waistcoat, and tall buckled boots",
        "an elegant gold-trimmed captain's uniform with a long coat",
    ],
    "wild_west_sheriff": [
        "a leather vest, a sheriff's star badge, a wide-brimmed cowboy hat, and a red bandana",
        "a long duster coat with spurred boots",
        "a sharp formal frontier suit with a sheriff's badge",
    ],
    "viking_warrior": [
        "fur-lined leather armor with braided rope details and a wolf-fur helmet",
        "engraved bronze armor with a horned helmet",
        "rugged battle-worn leather and chainmail with a fur cloak",
    ],
    "superhero": [
        "a sleek futuristic suit with a flowing cape and a glowing emblem on the chest",
        "a streamlined armored supersuit with glowing energy lines",
        "a classic heroic costume with a flowing cape and bold emblem",
    ],
    "mermaid_underwater": [
        "a shimmering, iridescent fish tail and a seashell-inspired top",
        "a pearl-encrusted tail with a coral tiara",
        "a glowing bioluminescent tail with flowing fins",
    ],
    "renaissance_royalty": [
        "a richly embroidered velvet gown or doublet with ornate golden jewelry and a delicate jeweled crown",
        "a regal fur-trimmed robe with an ornate medallion",
        "an elaborate lace-collared gown or doublet with a jeweled sash",
    ],
    "gatsby_1920s": [
        "an elegant sequined flapper dress with a feather headband, or a sharp pinstripe suit with a fedora hat",
        "a fringed art deco gown or a sharp tuxedo with suspenders",
        "a beaded silk dress or a classic three-piece suit with a pocket watch",
    ],
    "safari_adventure": [
        "khaki safari gear, a wide-brimmed explorer hat, and sturdy hiking boots",
        "a rugged safari vest with rolled sleeves and cargo pants",
        "a light expedition outfit with a neck scarf and sun hat",
    ],
    "winter_wonderland_santa": [
        "a cozy red and white Santa-inspired outfit with fluffy white trim",
        "a festive knitted sweater with a Santa hat",
        "an elegant winter coat with fur trim and a scarf",
    ],
    "tropical_beach_paradise": [
        "a colorful Hawaiian shirt or breezy summer outfit with a flower lei or sun hat",
        "a flowing beach sarong or linen shirt with sunglasses",
        "a bright tropical swimsuit cover-up with a straw hat",
    ],
    "disco_70s": [
        "a shiny sequined jumpsuit or flared bell-bottoms with a bold patterned shirt, big collar, and platform shoes",
        "a glittery halter top with wide-leg pants",
        "a velvet suit with a wide collar and platform boots",
    ],
    "scifi_mech_pilot": [
        "a sleek high-tech flight suit with glowing blue circuit details and a futuristic chest plate",
        "an armored exosuit with glowing power cells",
        "a streamlined pilot uniform with a holographic visor helmet under one arm",
    ],
    "fairy_tale_forest": [
        "an elegant woodland outfit made of soft fabrics, leaves, and vines, with delicate pointed ears",
        "a flowing moss-green gown with floral accents",
        "a rustic forest cloak with leaf embroidery",
    ],
    "egyptian_pharaoh": [
        "a golden ornate headdress, a wide jeweled collar necklace, and flowing white linen robes",
        "a regal gold-trimmed kilt with an ornate pectoral",
        "an elaborate ceremonial robe with golden armbands",
    ],
}

BACKGROUND_POOLS = {
    "dino_ritt": [
        "a dense tropical jungle with giant ferns and ancient trees, dramatic sun rays cutting through the canopy",
        "a misty prehistoric swamp with towering cycads and distant volcanoes",
        "a rocky canyon trail at the edge of the jungle with waterfalls in the distance",
    ],
    "astronaut": [
        "floating inside the International Space Station with Earth visible through a large window",
        "on a spacewalk just outside the station with Earth looming below",
        "standing on the dusty grey surface of the Moon with a lunar lander nearby",
    ],
    "cyberpunk": [
        "a rain-slicked neon-lit alleyway of Neo-Tokyo at night",
        "a crowded futuristic market street glowing with holographic signs",
        "a rooftop overlooking a sprawling cyberpunk skyline at night",
    ],
    "medieval_knight": [
        "the stone courtyard of an ancient fantasy castle during golden hour",
        "a misty battlefield at dawn with banners in the distance",
        "the grand throne room of a medieval castle",
    ],
    "pirate_captain": [
        "the wooden deck of a galleon ship at sunset, stormy ocean waves behind them",
        "a hidden tropical cove with a shipwreck in the background",
        "a bustling pirate harbor town at dusk",
    ],
    "wild_west_sheriff": [
        "a dusty frontier town main street, wooden saloon buildings",
        "a desert canyon at sunset with a lone cactus",
        "the porch of an old wooden saloon",
    ],
    "viking_warrior": [
        "a misty fjord landscape, longships on the water, stormy skies overhead",
        "a snow-covered Nordic village at dusk",
        "a rocky coastal cliff overlooking a stormy sea",
    ],
    "superhero": [
        "a dramatic city skyline at dusk, dynamic light streaks across the clouds",
        "above the clouds with a city sprawling below",
        "a dramatic rooftop overlooking a glowing city at night",
    ],
    "mermaid_underwater": [
        "a vibrant coral reef, schools of colorful fish, sunlight rays piercing from above",
        "a mysterious underwater cave glowing with bioluminescent light",
        "a sunken shipwreck surrounded by coral",
    ],
    "renaissance_royalty": [
        "a grand palace hall with classical paintings, golden chandeliers, heavy drapery",
        "an opulent royal garden with marble fountains",
        "a grand library filled with old tomes and gilded shelves",
    ],
    "gatsby_1920s": [
        "an opulent Art Deco ballroom, golden light fixtures, champagne glasses, confetti drifting in the air",
        "a glamorous rooftop party overlooking a 1920s city skyline at night",
        "an elegant jazz club with a live band on stage",
    ],
    "safari_adventure": [
        "the golden African savanna at sunset, acacia trees, distant wildlife silhouettes",
        "a dense jungle riverbank with exotic birds nearby",
        "a dusty safari jeep trail with mountains in the distance",
    ],
    "winter_wonderland_santa": [
        "a magical winter wonderland village, twinkling fairy lights, decorated pine trees, a cozy snow-covered cabin",
        "a snowy mountain village square with a giant decorated Christmas tree",
        "a cozy fireplace living room decorated for the holidays",
    ],
    "tropical_beach_paradise": [
        "a stunning turquoise beach, white sand, palm trees, vivid sunset sky",
        "a tropical beach bar with tiki torches at dusk",
        "a secluded lagoon surrounded by palm trees",
    ],
    "disco_70s": [
        "a colorful retro disco dance floor, a glowing mirror ball, neon light beams",
        "a vibrant 70s nightclub stage with funky lighting",
        "a retro roller disco rink with neon lights",
    ],
    "scifi_mech_pilot": [
        "the open cockpit of a massive futuristic robot mech inside a hangar bay, holographic control displays glowing nearby",
        "a futuristic launch bay with mechs lined up",
        "the cockpit mid-flight over a futuristic city skyline",
    ],
    "fairy_tale_forest": [
        "a glowing enchanted forest, magical floating lights, ancient mossy trees, soft mystical fog",
        "a moonlit forest clearing with glowing mushrooms",
        "an ancient tree hollow glowing with fairy lights",
    ],
    "egyptian_pharaoh": [
        "a grand desert temple, massive stone hieroglyph-covered columns, pyramids visible at golden hour",
        "the grand hall of an ancient pyramid lit by torches",
        "the banks of the Nile at sunset with temples in the distance",
    ],
}

PROP_POOLS = {
    "dino_ritt": ["glowing explorer torches", "weathered wooden walking sticks", "ancient dinosaur bones", "an old brass compass", "a rolled-up explorer map"],
    "astronaut": ["a handheld radio transmitter", "a small tool kit", "a sample collection container", "a NASA mission patch badge", "a small satellite model"],
    "cyberpunk": ["a glowing holographic device", "a sleek cyber-blade", "a futuristic energy drink canister", "a glowing data-chip", "a compact drone controller"],
    "medieval_knight": ["a longsword", "a heraldic shield", "a battle lance", "an ornate war horn", "a leather-bound scroll"],
    "pirate_captain": ["an antique cutlass", "a glowing lantern", "a weathered treasure map", "a brass spyglass", "a small chest of gold coins"],
    "wild_west_sheriff": ["an old revolver", "a coiled lasso rope", "a tin sheriff's badge", "a worn leather wanted poster", "a horseshoe"],
    "viking_warrior": ["a battle axe", "a round wooden shield carved with runes", "a war horn", "a carved wooden drinking cup", "a rune-engraved dagger"],
    "superhero": ["a glowing energy shield", "a high-tech grappling device", "a glowing emblem badge", "a futuristic communicator", "a heroic cape clasp"],
    "mermaid_underwater": ["a glowing pearl", "an ornate trident", "a seashell horn", "a string of pearls", "a piece of coral jewelry"],
    "renaissance_royalty": ["a golden goblet", "an ornate scepter", "a feathered fan", "a jeweled hand mirror", "a sealed royal scroll"],
    "gatsby_1920s": ["a glass of champagne", "a feathered fan", "a string of pearls", "a vintage cigarette holder", "a jeweled clutch purse"],
    "safari_adventure": ["binoculars", "a worn leather field journal", "a vintage camera", "a compass", "a canteen"],
    "winter_wonderland_santa": ["a beautifully wrapped gift", "a steaming mug of hot cocoa", "a string of jingle bells", "a candy cane", "a festive lantern"],
    "tropical_beach_paradise": ["a fresh tropical cocktail with a paper umbrella", "a beach ball", "a surfboard", "a snorkel mask", "a woven beach bag"],
    "disco_70s": ["a glowing disco ball pendant", "retro sunglasses", "a vinyl record", "a feather boa", "a vintage microphone"],
    "scifi_mech_pilot": ["a holographic tablet", "a glowing control joystick", "a futuristic tool device", "a mech access keycard", "a compact energy core"],
    "fairy_tale_forest": ["a glowing firefly lantern", "a carved wooden staff", "a flower crown", "a magical floating orb", "a delicate vine bracelet"],
    "egyptian_pharaoh": ["a golden ankh", "a ceremonial staff", "a jeweled scarab amulet", "an ornate fan", "a golden sistrum"],
}

# Platzhalter-Name -> zugehöriges Pool-Dict. Generisch für alle Themen -
# fehlt ein Pool für ein Thema/Platzhalter, bleibt der Platzhalter-Text
# unverändert im Prompt (sollte nicht vorkommen, da jeder Pool alle
# relevanten Themen abdeckt).
_VARIANT_PLACEHOLDERS = {
    "{ACTION}": ACTION_POOLS,
    "{CLOTHING}": CLOTHING_POOLS,
    "{BACKGROUND}": BACKGROUND_POOLS,
    "{PROP}": PROP_POOLS,
}


def _randomize_action(theme_id: str, prompt: str) -> str:
    """Ersetzt alle vorhandenen Varianz-Platzhalter ({ACTION}, {CLOTHING},
    {BACKGROUND}, {PROP}) durch zufällig gewählte, themapassende Texte -
    damit Pose, Kleidung, Schauplatz UND Requisite sich zwischen
    Generierungen unterscheiden, statt immer identisch zu sein."""
    for placeholder, pools in _VARIANT_PLACEHOLDERS.items():
        if placeholder not in prompt:
            continue
        pool = pools.get(theme_id, ["standing confidently, looking directly at the camera"])
        prompt = prompt.replace(placeholder, random.choice(pool))
    return prompt

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

    # Helme/Masken/Visiere, die das Gesicht stark verdecken, verhindern, dass
    # Schritt 2 (Face-Swap) das echte Gesicht zuverlässig übertragen kann -
    # das Ergebnis behält dann das generische, hier erzeugte Gesicht statt
    # des echten. Deshalb unabhängig vom jeweiligen Thema/Kostüm verlangen,
    # dass Gesichter klar sichtbar bleiben.
    visibility_clause = (
        "Every person's face must stay fully visible and unobstructed - no helmets, "
        "masks, full-face visors, or hoods covering any part of the face, even if "
        "the costume would normally include one. "
    )
    return gender_clause + visibility_clause + count_clause + prompt


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
            "image_urls": [image_url],
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
