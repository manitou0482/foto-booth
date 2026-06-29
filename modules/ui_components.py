"""Wiederverwendbare UI-Bausteine: Countdown, Theme-Auswahl, QR-Code,
Druck-Button (window.print()) und Teilen-Buttons (WhatsApp/E-Mail)."""
import io
import json
import time
import urllib.parse

import qrcode
import streamlit as st


@st.cache_data
def load_themes():
    with open("prompts.json", "r", encoding="utf-8") as f:
        return json.load(f)


def render_theme_picker(themes, on_select):
    """Zeigt die Themen als Grid aus Buttons. Ruft on_select(theme_id) auf."""
    st.subheader("Wähle dein Abenteuer ✨")
    cols_per_row = 4
    for i in range(0, len(themes), cols_per_row):
        row = themes[i : i + cols_per_row]
        cols = st.columns(len(row))
        for col, theme in zip(cols, row):
            with col:
                if st.button(theme["label"], key=f"theme_{theme['id']}", use_container_width=True):
                    on_select(theme["id"])
                    st.rerun()


def render_countdown(seconds: int = 3):
    """Rein visueller Countdown. Löst die Kamera NICHT automatisch aus -
    danach muss der Gast den nativen st.camera_input-Button selbst tippen."""
    placeholder = st.empty()
    for i in range(seconds, 0, -1):
        placeholder.markdown(
            f"<h1 style='font-size:12rem; text-align:center; margin:0;'>{i}</h1>",
            unsafe_allow_html=True,
        )
        time.sleep(1)
    placeholder.markdown(
        "<h1 style='font-size:5rem; text-align:center; margin:0;'>📸 Lächeln!</h1>",
        unsafe_allow_html=True,
    )
    time.sleep(0.5)
    placeholder.empty()


def make_qr_png(url: str) -> bytes:
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def render_result(result_url: str):
    """Zeigt das Ergebnisbild + QR-Code + Druck-Button + Teilen-Buttons."""
    col1, col2 = st.columns([2, 1])

    with col1:
        st.image(result_url, caption="Dein KI-Foto", use_container_width=True)

    with col2:
        st.write("📱 Scanne, um dein Foto herunterzuladen:")
        qr_png = make_qr_png(result_url)
        st.image(qr_png, width=220)

        if st.button("Foto drucken 🖨️", use_container_width=True):
            st.components.v1.html("<script>window.print();</script>", height=0)
            st.info(
                "Druckdialog wurde geöffnet (falls dein Browser das unterstützt). "
                "Wähle dort den Canon Selphy CP1200 im WLAN aus."
            )

        share_text = urllib.parse.quote(f"Schau dir mein KI-Fotobox-Bild an: {result_url}")
        st.link_button("📲 Per WhatsApp teilen", f"https://wa.me/?text={share_text}", use_container_width=True)
        st.link_button(
            "📧 Per E-Mail teilen",
            f"mailto:?subject=Mein%20Fotobox-Bild&body={share_text}",
            use_container_width=True,
        )
