"""Wonderbox – Streamlit-Einstiegspunkt.

Routing: Sidebar-Admin-Schalter wählt "1 Gerät" (All-in-One) oder
"2 Geräte" (Kamera + Bildschirm getrennt). Bei 2 Geräten wählt jedes Gerät
seine Rolle über den URL-Query-Parameter ?role=camera bzw. ?role=display.
"""
import os

import streamlit as st

from modules.state import get_shared_state, get_session_state, get_admin_settings
from modules.ui_components import load_themes, render_title
from modules import camera_view, display_view

st.set_page_config(page_title="Wonderbox", page_icon="✨", layout="wide")

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
admin_settings = get_admin_settings()

st.sidebar.title("⚙️ Admin")
mode = st.sidebar.radio(
    "Aufbau",
    ["1 Gerät", "2 Geräte"],
)

camera_label = st.sidebar.radio(
    "Kamera am Smartphone",
    ["Rückkamera", "Frontkamera"],
    index=0 if admin_settings.camera_facing == "environment" else 1,
)
admin_settings.camera_facing = "environment" if camera_label == "Rückkamera" else "user"

quality_label = st.sidebar.radio(
    "Bildqualität",
    ["Schnell (Party)", "Hohe Qualität (Pro)"],
    index=0 if admin_settings.scene_quality == "dev" else 1,
)
admin_settings.scene_quality = "dev" if quality_label == "Schnell (Party)" else "pro"

if mode == "1 Gerät":
    state = get_session_state()
    camera_view.render(state, themes, admin_settings, all_in_one=True)

else:
    state = get_shared_state()
    role = st.query_params.get("role")

    if role not in ("camera", "display"):
        render_title()
        st.markdown("<p style='text-align:center;'>Was ist das hier?</p>", unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📷 Kamera", use_container_width=True):
                st.query_params["role"] = "camera"
                st.rerun()
        with col2:
            if st.button("🖥️ Bildschirm", use_container_width=True):
                st.query_params["role"] = "display"
                st.rerun()
        st.stop()

    elif role == "camera":
        camera_view.render(state, themes, admin_settings, all_in_one=False)
    else:
        display_view.render(state, themes)
