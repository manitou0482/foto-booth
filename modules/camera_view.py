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
    """Gemeinsamer Ablauf für Bereit-Bestätigung -> Countdown -> Aufnahme ->
    KI-Verarbeitung -> Ergebnis. Wird sowohl im All-in-One- als auch im
    Kamera-Rollen-Modus genutzt."""
    if state.phase == "idle":
        st.info(waiting_message)

    elif state.phase == "theme_selected":
        st.markdown(
            "<h2 style='text-align:center;'>📸 Bereit?</h2>"
            "<p style='text-align:center;'>Stellt euch auf und tippt los!</p>",
            unsafe_allow_html=True,
        )
        if st.button("📸 Foto machen!", use_container_width=True, type="primary"):
            state.phase = "countdown"
            st.rerun()

    elif state.phase == "countdown":
        ui_components.render_countdown(3)
        state.capture_token = str(time.time())
        state.phase = "captured_ready"
        st.rerun()

    elif state.phase == "captured_ready":
        # key enthält das Token, damit Streamlit die Komponente jede Runde als
        # NEUES Widget behandelt - sonst könnte intern noch ein Rückgabewert
        # einer früheren Runde am alten, gleichbleibenden Key hängen bleiben
        # und versehentlich für die aktuelle Aufnahme verwendet werden.
        photo_base64 = camera_component.camera_widget(
            trigger_token=state.capture_token,
            key=f"booth_camera_{state.capture_token}",
            facing_mode=admin_settings.camera_facing,
        )
        if photo_base64:
            state.captured_image_bytes = base64.b64decode(photo_base64)
            state.phase = "processing"
            st.rerun()

    elif state.phase == "processing":
        st.image(state.captured_image_bytes, caption="So wurde dein Foto aufgenommen", width=220)
        placeholder = st.empty()
        with placeholder:
            ui_components.render_loading_spinner()
        theme = next(t for t in themes if t["id"] == state.theme_id)
        try:
            url = fal_client.generate_image(state.captured_image_bytes, theme["prompt"], theme["id"])
            state.result_image_url = url
        except Exception as e:
            state.error = str(e)
        placeholder.empty()
        state.phase = "result"
        st.rerun()

    elif state.phase == "result":
        if state.error:
            st.error(f"Fehler bei der KI-Generierung: {state.error}")
        else:
            ui_components.render_result(state.result_image_url, state.captured_image_bytes)


def _render_all_in_one(state, themes, admin_settings):
    ui_components.render_title()

    if state.phase == "idle":
        ui_components.render_theme_picker(themes, on_select=lambda tid: _start_theme(state, tid))
    else:
        _run_capture_flow(state, themes, admin_settings, waiting_message="")
        if state.phase == "result":
            if st.button("🔄 Neues Foto"):
                state.reset()
                st.rerun()


def _render_camera_role(state, themes, admin_settings):
    ui_components.render_title()

    # Nur im Leerlauf pollen: Sobald ein Thema gewählt wurde, treibt sich der
    # Ablauf über die eigenen st.rerun()-Aufrufe selbst voran (Bereit-Check,
    # Countdown, KI-Verarbeitung). Würde hier weiterhin alle 1,5s automatisch
    # neu geladen, würde das mehrsekündige Abläufe immer wieder mitten im
    # Lauf abbrechen und neu starten.
    if state.phase == "idle":
        st_autorefresh(interval=1500, key="camera_poll")

    _run_capture_flow(state, themes, admin_settings, waiting_message="Warte auf Themenwahl...")

    if state.phase == "result":
        st.success("Fertig! Ergebnis auch auf dem Bildschirm.")
        if st.button("🔄 Nächste Runde"):
            state.reset()
            st.rerun()
