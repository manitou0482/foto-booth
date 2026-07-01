"""Pipeline: Foto → FLUX.2 Szene → Face-Swap → finale URL.

Der API-Key wird ausschließlich über st.secrets["FAL_KEY"] gelesen
(siehe app.py) und niemals im Code hinterlegt.
"""
import io
import random

import fal_client
from PIL import Image

SCENE_ENDPOINTS = {
    "dev": "fal-ai/flux-2/edit",
    "pro": "fal-ai/flux-2-pro/edit",
}

FACESWAP_ENDPOINT = "easel-ai/advanced-face-swap"

MAX_DIMENSION = 1024

_COUNT_PREFIXES = {
    1: "1person, solo, only one person, single subject, do not add any other people, ",
    2: "2people, exactly two people, only two people, duo, do not add any other people, ",
    3: "3people, exactly three people, only three people, trio, do not add any other people, ",
    4: "4people, exactly four people, only four people, do not add any other people, ",
}


def _resize_for_upload(image_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img.thumbnail((MAX_DIMENSION, MAX_DIMENSION))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _output_size(image_bytes: bytes) -> dict:
    img = Image.open(io.BytesIO(image_bytes))
    w, h = img.size
    if w >= h:
        out_w = MAX_DIMENSION
        out_h = round(h / w * MAX_DIMENSION / 16) * 16
    else:
        out_h = MAX_DIMENSION
        out_w = round(w / h * MAX_DIMENSION / 16) * 16
    return {"width": max(out_w, 16), "height": max(out_h, 16)}


def face_swap(source_url: str, target_url: str) -> str:
    """Überträgt Gesichter aus source_url auf target_url via easel-ai/advanced-face-swap."""
    result = fal_client.run(
        FACESWAP_ENDPOINT,
        arguments={
            "face_image_0": {"url": source_url},
            "gender_0": "non-binary",
            "target_image": {"url": target_url},
            "workflow_type": "target_hair",
        },
    )
    return result["image"]["url"]


def generate_image(image_bytes: bytes, prompt: str, quality: str = "dev", num_people: int = 1) -> tuple[str, str]:
    """Gibt (image_url, scene_url) zurück.
    image_url = hochgeladenes Originalfoto (für Face-Swap),
    scene_url = FLUX.2-Ergebnis."""
    print(f"[generate_image] Start — quality={quality}, num_people={num_people}")
    resized_bytes = _resize_for_upload(image_bytes)
    print("[generate_image] Upload startet ...")
    image_url = fal_client.upload(resized_bytes, "image/jpeg")
    print(f"[generate_image] Upload fertig: {image_url}")
    size = _output_size(image_bytes)

    count_prefix = _COUNT_PREFIXES.get(
        num_people,
        f"{num_people}people, exactly {num_people} people, only {num_people} people, do not add any other people, "
    )
    full_prompt = count_prefix + prompt

    print(f"[generate_image] FLUX.2 startet — endpoint={SCENE_ENDPOINTS[quality]}")
    scene_result = fal_client.run(
        SCENE_ENDPOINTS[quality],
        arguments={
            "prompt": full_prompt,
            "image_urls": [image_url],
            "image_size": size,
            "seed": random.randint(1, 99999999),
        },
    )
    scene_url = scene_result["images"][0]["url"]
    print(f"[generate_image] FLUX.2 fertig: {scene_url}")
    return image_url, scene_url
