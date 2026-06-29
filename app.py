"""Wunderbox – Streamlit-Einstiegspunkt.

Routing: Sidebar-Admin-Schalter wählt Modus 1 (All-in-One) oder Modus 2
(Zwei-Geräte-Station). In Modus 2 wählt jedes Gerät seine Rolle über den
URL-Query-Parameter ?role=camera bzw. ?role=display.
"""
import os

import streamlit as st

from modules.state import get_shared_state, get_session_state
from modules.ui_components import load_themes
from modules import camera_view, display_view

st.set_page_config(page_title="Wunderbox", page_icon="✨", layout="wide")

# PRELIGN-CI: Dunkelviolett (#2A1538) + Gold (#D4B05A), abgerundete Formen.
st.markdown(
    """
    <style>
    div.stButton > button {
        border-radius: 28px;
        border: 1px solid rgba(212, 176, 90, 0.4);
    }
    div.stButton > button[kind="primary"] {
        background-color: #D4B05A;
        color: #2A1538;
        border: none;
        font-weight: 600;
    }
    div.stButton > button[kind="primary"]:hover {
        background-color: #C9A84D;
        color: #2A1538;
    }
    img {
        border-radius: 20px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# fal_client liest den Key automatisch aus der Umgebungsvariable FAL_KEY.
if "FAL_KEY" in st.secrets:
    os.environ["FAL_KEY"] = st.secrets["FAL_KEY"]
else:
    st.error(
        "FAL_KEY fehlt in den Streamlit-Secrets! Bitte in .streamlit/secrets.toml "
        "(lokal) bzw. in den App-Secrets der Streamlit Community Cloud hinterlegen."
    )
    st.stop()

themes = load_themes()

st.sidebar.title("⚙️ Admin")
mode = st.sidebar.radio(
    "Betriebsmodus",
    ["Modus 1: All-in-One", "Modus 2: Zwei-Geräte-Station"],
)

if mode.startswith("Modus 1"):
    state = get_session_state()
    camera_view.render(state, themes, all_in_one=True)

else:
    state = get_shared_state()
    role = st.query_params.get("role")

    if role not in ("camera", "display"):
        st.title("✨ Wunderbox")
        st.write("Welche Rolle übernimmt dieses Gerät?")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📷 Ich bin die Kamera (Smartphone)", use_container_width=True):
                st.query_params["role"] = "camera"
                st.rerun()
        with col2:
            if st.button("🖥️ Ich bin die Anzeige (Tablet)", use_container_width=True):
                st.query_params["role"] = "display"
                st.rerun()
        st.stop()

    elif role == "camera":
        camera_view.render(state, themes, all_in_one=False)
    else:
        display_view.render(state, themes)
