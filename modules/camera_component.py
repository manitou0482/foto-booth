"""Eigene Kamera-Komponente, da Streamlits st.camera_input keinen
zuverlässigen, automatischen Auslöser unterstützt (Klick-Simulation auf den
internen "Take Photo"-Button war fragil und hat in der Praxis nicht
zuverlässig funktioniert). Diese Komponente läuft direkt im Browser
(getUserMedia + Canvas) und nimmt das Foto exakt dann auf, wenn sich
trigger_token ändert - ganz ohne Button-Klick-Hacks.
"""
import os

import streamlit.components.v1 as components

_COMPONENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "camera_frontend")
_component_func = components.declare_component("ki_fotobox_camera", path=_COMPONENT_DIR)


def camera_widget(trigger_token: str, key: str, facing_mode: str = "environment") -> str | None:
    """Rendert die Live-Kameravorschau. facing_mode steuert, welche Kamera
    geöffnet wird ("environment" = Rückkamera, "user" = Frontkamera) - vom
    Admin in der Sidebar fest eingestellt, ohne dass Gäste etwas auswählen
    müssen. Gibt das aufgenommene Foto als Base64-JPEG zurück, sobald
    trigger_token sich geändert hat und die Aufnahme erfolgt ist - sonst None."""
    return _component_func(trigger_token=trigger_token, facing_mode=facing_mode, key=key, default=None)
