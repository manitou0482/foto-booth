"""Einfache Pipeline: Foto hochladen → FLUX.2 → URL zurückgeben.

Der API-Key wird ausschließlich über st.secrets["FAL_KEY"] gelesen
(siehe app.py) und niemals im Code hinterlegt.
"""
import io
import random

import fal_client
from PIL import Image

try:
    import cv2
    import mediapipe as mp
    import numpy as np
    _COUNT_AVAILABLE = True
except ImportError:
    _COUNT_AVAILABLE = False

SCENE_ENDPOINTS = {
    "dev": "fal-ai/flux-2/edit",
    "pro": "fal-ai/flux-2-pro/edit",
}

MAX_DIMENSION = 1024

# Boostwords je Personenzahl — ganz vorne im Prompt,
# FLUX.2 gewichtet frühe Tokens stärker
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


def _count_faces(image_bytes: bytes) -> int:
    """Zählt Gesichter via MediaPipe FaceMesh. Gibt 0 zurück wenn nicht verfügbar."""
    if not _COUNT_AVAILABLE:
        return 0
    arr = np.frombuffer(image_bytes, np.uint8)
    bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    with mp.solutions.face_mesh.FaceMesh(
        max_num_faces=8,
        refine_landmarks=False,
        min_detection_confidence=0.4,
    ) as fm:
        res = fm.process(rgb)
    return len(res.multi_face_landmarks) if res.multi_face_landmarks else 0


def debug_count(image_bytes: bytes) -> dict:
    """Gibt Debug-Info zurück: ob MediaPipe verfügbar ist und wie viele Gesichter erkannt wurden."""
    n = _count_faces(image_bytes) if _COUNT_AVAILABLE else -1
    return {"available": _COUNT_AVAILABLE, "faces": n}


def generate_image(image_bytes: bytes, prompt: str, quality: str = "dev") -> str:
    resized_bytes = _resize_for_upload(image_bytes)
    image_url = fal_client.upload(resized_bytes, "image/jpeg")
    size = _output_size(image_bytes)

    n = _count_faces(resized_bytes)
    count_prefix = _COUNT_PREFIXES.get(n, f"{n}people, exactly {n} people, only {n} people, do not add any other people, ") if n > 0 else ""

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
    return result["images"][0]["url"]
