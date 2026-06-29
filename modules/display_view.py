"""Anzeige-/Buzzer-Ansicht für Modus 2, Rolle 'display' (Tablet)."""
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from modules import ui_components


def _start_theme(state, theme_id):
    state.theme_id = theme_id
    state.phase = "theme_selected"


def render(state, themes):
    ui_components.render_title()
    st_autorefresh(interval=1500, key="display_poll")

    if state.phase == "idle":
        ui_components.render_theme_picker(themes, on_select=lambda tid: _start_theme(state, tid))

    elif state.phase in ("theme_selected", "countdown", "captured_ready"):
        st.info("📷 Schau in die Kamera!")

    elif state.phase == "processing":
        st.info("✨ Einen Moment...")

    elif state.phase == "result":
        if state.error:
            st.error(f"Fehler: {state.error}")
        else:
            ui_components.render_result(state.result_image_url)
        if st.button("🔄 Nächste Runde"):
            state.reset()
            st.rerun()
