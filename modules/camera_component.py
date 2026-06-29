"""Python-Anbindung der eigenen Kamera-Komponente (modules/camera_frontend/).

Ersetzt st.camera_input, weil dieses keine Auswahl einer bestimmten Kamera
unterstützt. Die Komponente läuft komplett im Browser (getUserMedia + Canvas),
erlaubt die feste Auswahl eines Kamera-Geräts und nimmt automatisch ein Foto
auf, sobald sich trigger_token ändert (z.B. nach Ablauf des Countdowns).
"""
import os

import streamlit.components.v1 as components

_COMPONENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "camera_frontend")
_component_func = components.declare_component("ki_fotobox_camera", path=_COMPONENT_DIR)

_DEFAULT_RESULT = {"devices": [], "photo_base64": None}


def camera_widget(preferred_label: str | None, trigger_token: str, key: str) -> dict:
    """Rendert die Live-Kameravorschau.

    Rückgabe: {"devices": [{"deviceId": ..., "label": ...}, ...], "photo_base64": str|None}
    """
    result = _component_func(
        preferred_label=preferred_label,
        trigger_token=trigger_token,
        key=key,
        default=_DEFAULT_RESULT,
    )
    return result or _DEFAULT_RESULT
