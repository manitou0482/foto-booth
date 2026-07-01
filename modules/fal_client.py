"""Einfache Pipeline: Foto hochladen → FLUX.2 → URL zurückgeben.

Der API-Key wird ausschließlich über st.secrets["FAL_KEY"] gelesen
(siehe app.py) und niemals im Code hinterlegt.
"""
import io
import random

import fal_client
import requests
from PIL import Image

SCENE_ENDPOINTS = {
    "dev": "fal-ai/flux-2/edit",
    "pro": "fal-ai/flux-2-pro/edit",
}

MAX_DIMENSION = 1024

MASTER_FRAMEWORK = (
    "Photorealistic cinematic photo. The people from @image1 looking directly at the camera "
    "with clear, well-lit facial expressions, faces fully visible. "
    "{prompt} "
    "Single cohesive photograph, not a collage or grid."
)


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


def generate_image(image_bytes: bytes, prompt: str, quality: str = "dev") -> str:
    resized_bytes = _resize_for_upload(image_bytes)
    image_url = fal_client.upload(resized_bytes, "image/jpeg")
    size = _output_size(image_bytes)

    full_prompt = MASTER_FRAMEWORK.format(prompt=prompt)

    result = fal_client.run(
        SCENE_ENDPOINTS[quality],
        arguments={
            "prompt": full_prompt,
            "image_urls": [image_url],
            "image_size": size,
            "seed": random.randint(1, 99999999),
        },
    )
    return result["images"][0]["url"]
