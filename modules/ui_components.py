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
    """Zeigt die Themen als Grid aus Buttons. Ruft on_select(theme_id) auf.

    Die Anzahl der Personen im Foto wird automatisch von fal_client erkannt
    (siehe modules/fal_client.py, _detect_num_people) - keine manuelle
    Auswahl nötig."""
    st.subheader("Wähle dein Abenteuer ✨")
    cols_per_row = 4
    for i in range(0, len(themes), cols_per_row):
        row = themes[i : i + cols_per_row]
        cols = st.columns(len(row))
        for col, theme in zip(cols, row):
            with col:
                preview_path = theme.get("preview")
                if preview_path:
                    st.image(preview_path, use_container_width=True)
                if st.button(theme["label"], key=f"theme_{theme['id']}", use_container_width=True):
                    on_select(theme["id"])
                    st.rerun()


def render_countdown(seconds: int = 3):
    """Visueller Countdown (3...2...1... Bitte lächeln!). Die eigentliche
    Aufnahme erfolgt direkt danach automatisch über modules/camera_component."""
    placeholder = st.empty()
    for i in range(seconds, 0, -1):
        placeholder.markdown(
            f"<h1 style='font-size:12rem; text-align:center; margin:0; color:#D4B05A;'>{i}</h1>",
            unsafe_allow_html=True,
        )
        time.sleep(1)
    placeholder.markdown(
        "<h1 style='font-size:5rem; text-align:center; margin:0; color:#D4B05A;'>📸 Bitte lächeln!</h1>",
        unsafe_allow_html=True,
    )
    time.sleep(0.5)
    placeholder.empty()


def render_loading_spinner():
    """Reiner, textloser Lade-Indikator (gedrehter Goldring) während die KI
    das Foto verarbeitet - passend zum PRELIGN-CI."""
    st.markdown(
        """
        <div style="display:flex; justify-content:center; align-items:center; height:220px;">
          <div style="width:64px; height:64px; border:6px solid rgba(212,176,90,0.25);
                      border-top-color:#D4B05A; border-radius:50%;
                      animation:ki-spin 1s linear infinite;"></div>
        </div>
        <style>
        @keyframes ki-spin { to { transform: rotate(360deg); } }
        </style>
        """,
        unsafe_allow_html=True,
    )


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
