"""Kamera-Ansicht: Modus 1 (All-in-One) und Modus 2 Rolle 'camera'."""
import base64
import time

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from modules import ui_components, fal_client, camera_component


def render(state, themes, admin_settings, all_in_one: bool):
    if all_in_one:
        _render_all_in_one(state, themes, admin_settings)
    else:
        _render_camera_role(state, themes, admin_settings)


def _start_theme(state, theme_id):
    state.theme_id = theme_id
    state.phase = "theme_selected"


def _run_capture_flow(state, themes, admin_settings, waiting_message: str):
    """Gemeinsamer Ablauf für countdown -> capture -> processing -> result,
    wird sowohl im All-in-One- als auch im Kamera-Rollen-Modus genutzt."""
    if state.phase == "idle":
        st.info(waiting_message)

    elif state.phase == "theme_selected":
        ui_components.render_countdown(3)
        state.capture_request_id = str(time.time())
        state.phase = "captured_ready"
        st.rerun()

    elif state.phase == "captured_ready":
        st.info("📸 Aufnahme läuft automatisch...")
        result = camera_component.camera_widget(
            preferred_label=admin_settings.preferred_camera_label,
            trigger_token=state.capture_request_id,
            key="booth_camera",
        )
        if result["devices"]:
            admin_settings.available_devices = result["devices"]
        if result["photo_base64"]:
            state.captured_image_bytes = base64.b64decode(result["photo_base64"])
            state.phase = "processing"
            st.rerun()

    elif state.phase == "processing":
        with st.spinner("✨ Die KI verwandelt euer Foto... (ca. 2-3 Sekunden)"):
            theme = next(t for t in themes if t["id"] == state.theme_id)
            try:
                url = fal_client.generate_image(state.captured_image_bytes, theme["prompt"])
                state.result_image_url = url
            except Exception as e:
                state.error = str(e)
            state.phase = "result"
        st.rerun()

    elif state.phase == "result":
        if state.error:
            st.error(f"Fehler bei der KI-Generierung: {state.error}")
        else:
            ui_components.render_result(state.result_image_url)


def _render_all_in_one(state, themes, admin_settings):
    st.title("📸 KI-Fotobox")

    if state.phase == "idle":
        ui_components.render_theme_picker(themes, on_select=lambda tid: _start_theme(state, tid))
    else:
        _run_capture_flow(state, themes, admin_settings, waiting_message="")
        if state.phase == "result":
            if st.button("🔄 Neues Foto"):
                state.reset()
                st.rerun()


def _render_camera_role(state, themes, admin_settings):
    st.title("📷 Kamera-Station")
    st_autorefresh(interval=1500, key="camera_poll")

    _run_capture_flow(state, themes, admin_settings, waiting_message="Warte auf Themenauswahl am Tablet...")

    if state.phase == "result":
        st.success("Fertig! Das Ergebnis erscheint auch auf dem Tablet.")
        if st.button("🔄 Bereit für die nächsten Gäste"):
            state.reset()
            st.rerun()
