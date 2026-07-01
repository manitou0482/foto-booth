"""Pipeline: Foto → FLUX.2 Szene → Replicate Face-Swap → finale URL.

API-Keys werden ausschließlich über st.secrets gelesen (siehe app.py)
und niemals im Code hinterlegt.
"""
import io
import random

import fal_client
import replicate
from PIL import Image

SCENE_ENDPOINTS = {
    "dev": "fal-ai/flux-2/edit",
    "pro": "fal-ai/flux-2-pro/edit",
}

FACESWAP_MODEL = "ddvinh1/tool-faceswap:eb7ba9899d3f4481d713288d937f337643c29e17a5214d70e65a696ffe53c915"

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


def face_swap(source_url: str, target_url: str, num_people: int = 1) -> str:
    """Überträgt Gesichter aus source_url auf target_url via Replicate.
    mode=single für 1 Person, mode=all für Gruppen."""
    mode = "single" if num_people == 1 else "all"
    output = replicate.run(
        FACESWAP_MODEL,
        input={
            "mode": mode,
            "source": source_url,
            "target": target_url,
            "is_use_mask": True,
        },
    )
    return output.url


def generate_image(image_bytes: bytes, prompt: str, quality: str = "dev", num_people: int = 1) -> tuple[str, str]:
    """Gibt (image_url, scene_url) zurück.
    image_url = hochgeladenes Originalfoto (für Face-Swap),
    scene_url = FLUX.2-Ergebnis."""
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
            "prompt": full_prompt,
            "image_urls": [image_url],
            "image_size": size,
            "seed": random.randint(1, 99999999),
        },
    )
    scene_url = result["images"][0]["url"]
    return image_url, scene_url
