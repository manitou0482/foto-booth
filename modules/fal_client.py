"""Pipeline: Foto → FLUX.2 → finale URL.

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


def generate_image(image_bytes: bytes, prompt: str, quality: str = "dev", num_people: int = 1) -> str:
    """Gibt result_url zurück: FLUX.2-generiertes Themenbild."""
    resized_bytes = _resize_for_upload(image_bytes)
    image_url = fal_client.upload(resized_bytes, "image/jpeg")
    size = _output_size(image_bytes)

    count_prefix = _COUNT_PREFIXES.get(
        num_people,
        f"{num_people}people, exactly {num_people} people, only {num_people} people, do not add any other people, "
    )
    full_prompt = count_prefix + prompt

    result = fal_client.run(
        SCENE_ENDPOINTS[quality],
        arguments={
            "image_urls": [image_url],
            "prompt": full_prompt,
            "image_size": size,
            "seed": random.randint(1, 99999999),
        },
    )
    return result["images"][0]["url"]
