"""Anzeige-/Buzzer-Ansicht für Modus 2, Rolle 'display' (Tablet)."""
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from modules import ui_components


def _start_theme(state, theme_id):
    state.theme_id = theme_id
    state.phase = "theme_selected"


def render(state, themes):
    st.title("✨ Wunderbox")
    st_autorefresh(interval=1500, key="display_poll")

    if state.phase == "idle":
        ui_components.render_theme_picker(themes, on_select=lambda tid: _start_theme(state, tid))

    elif state.phase in ("theme_selected", "countdown", "captured_ready"):
        st.info("📷 Schau in die Kamera oben in der Box! Countdown läuft dort gerade...")

    elif state.phase == "processing":
        st.info("✨ Die KI verwandelt euer Foto, einen Moment...")

    elif state.phase == "result":
        if state.error:
            st.error(f"Fehler bei der KI-Generierung: {state.error}")
        else:
            ui_components.render_result(state.result_image_url)
        if st.button("🔄 Nächste Gäste / Neue Runde"):
            state.reset()
            st.rerun()
