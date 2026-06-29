"""DIY-KI-Fotobox – Streamlit-Einstiegspunkt.

Routing: Sidebar-Admin-Schalter wählt Modus 1 (All-in-One) oder Modus 2
(Zwei-Geräte-Station). In Modus 2 wählt jedes Gerät seine Rolle über den
URL-Query-Parameter ?role=camera bzw. ?role=display.
"""
import os

import streamlit as st

from modules.state import get_shared_state, get_session_state, get_admin_settings
from modules.ui_components import load_themes
from modules import camera_view, display_view

st.set_page_config(page_title="KI-Fotobox", page_icon="📸", layout="wide")

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
    "Betriebsmodus",
    ["Modus 1: All-in-One", "Modus 2: Zwei-Geräte-Station"],
)

st.sidebar.subheader("📷 Kamera-Einstellung")
device_labels = [d["label"] or f"Kamera {i + 1}" for i, d in enumerate(admin_settings.available_devices)]
camera_options = ["(Automatisch)"] + device_labels
current_index = (
    camera_options.index(admin_settings.preferred_camera_label)
    if admin_settings.preferred_camera_label in camera_options
    else 0
)
camera_choice = st.sidebar.selectbox("Feste Kamera für die Box", camera_options, index=current_index)
admin_settings.preferred_camera_label = None if camera_choice == "(Automatisch)" else camera_choice
if not admin_settings.available_devices:
    st.sidebar.caption("Liste erscheint, sobald die Kamera einmal aktiviert wurde.")

if mode.startswith("Modus 1"):
    state = get_session_state()
    camera_view.render(state, themes, admin_settings, all_in_one=True)

else:
    state = get_shared_state()
    role = st.query_params.get("role")

    if role not in ("camera", "display"):
        st.title("📸 KI-Fotobox – Zwei-Geräte-Modus")
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
        camera_view.render(state, themes, admin_settings, all_in_one=False)
    else:
        display_view.render(state, themes)
