"""Wiederverwendbare UI-Bausteine: Countdown, Theme-Auswahl, QR-Code,
Druck-Button (window.print()) und Teilen-Buttons (WhatsApp/E-Mail)."""
import base64
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


@st.cache_data
def _image_data_uri(path: str) -> str:
    """Liest ein lokales Bild ein und kodiert es als data:-URI, damit es in
    einen klickbaren <a><img></a>-Link eingebettet werden kann - Streamlit
    kann lokale Dateipfade sonst nicht direkt als <img src> servieren."""
    with open(path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _build_href(extra_params: dict) -> str:
    """Baut einen Link auf die aktuelle Seite, der alle bestehenden
    Query-Parameter (z.B. ?role=camera in Modus 2) erhält und zusätzlich
    die übergebenen Parameter setzt."""
    params = dict(st.query_params)
    params.update(extra_params)
    return "?" + urllib.parse.urlencode(params)


def render_title():
    """Zentrierter App-Titel, einheitlich auf allen Bildschirmen."""
    st.markdown(
        "<h1 style='text-align:center; color:#D4B05A; margin-bottom:0.2em;'>✨ Wonderbox</h1>",
        unsafe_allow_html=True,
    )


def render_theme_picker(themes, on_select):
    """Zeigt die Themen als Grid aus klickbaren Vorschaubildern (kein
    separater "Auswählen"-Button mehr - ein Tap auf das Bild wählt das
    Thema direkt). Ruft on_select(theme_id) auf.

    Die Anzahl der Personen im Foto wird automatisch von fal_client erkannt
    (siehe modules/fal_client.py, _detect_num_people) - keine manuelle
    Auswahl nötig."""
    selected_theme = st.query_params.get("selected_theme")
    if selected_theme:
        del st.query_params["selected_theme"]
        on_select(selected_theme)
        st.rerun()
        return

    cols_per_row = 4
    for i in range(0, len(themes), cols_per_row):
        row = themes[i : i + cols_per_row]
        cols = st.columns(len(row))
        for col, theme in zip(cols, row):
            with col:
                preview_path = theme.get("preview")
                if preview_path:
                    href = _build_href({"selected_theme": theme["id"]})
                    data_uri = _image_data_uri(preview_path)
                    st.markdown(
                        f'<a href="{href}" target="_self">'
                        f'<img src="{data_uri}" style="width:100%; border-radius:20px; '
                        f'cursor:pointer; display:block;"></a>',
                        unsafe_allow_html=True,
                    )


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


def render_result(result_url: str, input_image_bytes: bytes | None = None):
    """Zeigt das Ergebnisbild + QR-Code + Druck-Button + Teilen-Buttons.
    input_image_bytes (optional): die Original-Aufnahme zum direkten
    Vergleich - hilfreich zur Fehlersuche, falls das Ergebnis nicht wie
    erwartet aussieht."""
    col1, col2 = st.columns([2, 1])

    with col1:
        st.image(result_url, caption="Dein Foto", use_container_width=True)
        if input_image_bytes:
            with st.expander("Original-Aufnahme anzeigen"):
                st.image(input_image_bytes, caption="So wurdest du fotografiert", width=300)

    with col2:
        st.write("📱 Foto herunterladen")
        qr_png = make_qr_png(result_url)
        st.image(qr_png, width=220)

        if st.button("🖨️ Drucken", use_container_width=True):
            st.components.v1.html("<script>window.print();</script>", height=0)
            st.info("Druckdialog geöffnet - Drucker auswählen.")

        share_text = urllib.parse.quote(f"Mein Wonderbox-Bild: {result_url}")

        phone = st.text_input(
            "📲 WhatsApp-Nummer (mit Ländervorwahl, z.B. 4915512345678)",
            key=f"whatsapp_phone_{result_url}",
            placeholder="4915512345678",
        )
        if st.button(
            "📲 Per WhatsApp senden",
            use_container_width=True,
            disabled=not phone.strip(),
            key=f"whatsapp_send_{result_url}",
        ):
            from modules import whatsapp_client
            with st.spinner("Wird gesendet..."):
                ok, err = whatsapp_client.send_image(phone, result_url)
            if ok:
                st.success("✅ Foto wurde per WhatsApp gesendet!")
            else:
                st.error(f"WhatsApp-Fehler: {err}")

        st.link_button(
            "📧 E-Mail",
            f"mailto:?subject=Mein%20Wonderbox-Bild&body={share_text}",
            use_container_width=True,
        )
