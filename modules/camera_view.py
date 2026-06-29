"""Kamera-Ansicht: Modus 1 (All-in-One) und Modus 2 Rolle 'camera'."""
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from modules import ui_components, fal_client


def render(state, themes, all_in_one: bool):
    if all_in_one:
        _render_all_in_one(state, themes)
    else:
        _render_camera_role(state, themes)


def _start_theme(state, theme_id):
    state.theme_id = theme_id
    state.phase = "theme_selected"


def _run_capture_flow(state, themes, waiting_message: str):
    """Gemeinsamer Ablauf für countdown -> capture -> processing -> result,
    wird sowohl im All-in-One- als auch im Kamera-Rollen-Modus genutzt."""
    if state.phase == "idle":
        st.info(waiting_message)

    elif state.phase == "theme_selected":
        ui_components.render_countdown(3)
        state.phase = "captured_ready"
        st.rerun()

    elif state.phase == "captured_ready":
        st.info("📸 Aufnahme läuft automatisch...")
        photo = st.camera_input("Kamera", label_visibility="collapsed")
        ui_components.render_auto_capture_trigger()
        if photo is not None:
            state.captured_image_bytes = photo.getvalue()
            state.phase = "processing"
            st.rerun()

    elif state.phase == "processing":
        with st.spinner("✨ Die KI verwandelt euer Foto... (kann ein paar Sekunden dauern)"):
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


def _render_all_in_one(state, themes):
    st.title("📸 KI-Fotobox")

    if state.phase == "idle":
        ui_components.render_theme_picker(themes, on_select=lambda tid: _start_theme(state, tid))
    else:
        _run_capture_flow(state, themes, waiting_message="")
        if state.phase == "result":
            if st.button("🔄 Neues Foto"):
                state.reset()
                st.rerun()


def _render_camera_role(state, themes):
    st.title("📷 Kamera-Station")

    # Nur im Leerlauf pollen: Sobald ein Thema gewählt wurde, treibt sich der
    # Ablauf über die eigenen st.rerun()-Aufrufe selbst voran (Countdown,
    # KI-Verarbeitung). Würde hier weiterhin alle 1,5s automatisch neu
    # geladen, würde das den mehrere Sekunden dauernden Countdown immer
    # wieder mitten im Lauf abbrechen und neu starten.
    if state.phase == "idle":
        st_autorefresh(interval=1500, key="camera_poll")

    _run_capture_flow(state, themes, waiting_message="Warte auf Themenauswahl am Tablet...")

    if state.phase == "result":
        st.success("Fertig! Das Ergebnis erscheint auch auf dem Tablet.")
        if st.button("🔄 Bereit für die nächsten Gäste"):
            state.reset()
            st.rerun()
