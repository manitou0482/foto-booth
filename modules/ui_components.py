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


def render_theme_picker(themes, state, on_select):
    """Zeigt zuerst die Personenanzahl-Auswahl, dann die Themen als Grid aus
    Buttons. Ruft on_select(theme_id) auf.

    Die Personenanzahl steuert, ob fal_client einen Mehrpersonen-Hinweis vor
    den Theme-Prompt setzt (siehe modules/fal_client.py) - ohne diesen
    Hinweis lässt die KI bei Themen mit Einzahl-Formulierung ("the person")
    weitere Personen aus dem Originalfoto einfach weg."""
    num_people_label = st.radio(
        "Wie viele Personen sind auf dem Foto?",
        ["1 Person", "2 Personen"],
        horizontal=True,
        key="num_people_choice",
    )
    state.num_people = 1 if num_people_label == "1 Person" else 2

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


def render_auto_capture_trigger():
    """Klickt den internen 'Take Photo'-Button von st.camera_input automatisch,
    sobald er im DOM erscheint - damit nach dem Countdown niemand mehr selbst
    auf den Auslöser tippen muss.

    Funktioniert, weil st.components.v1.html ein Iframe rendert, das über
    window.parent.document Zugriff auf die Hauptseite hat. Das ist KEIN
    offiziell dokumentiertes Streamlit-Feature - es verlässt sich auf den
    aktuell stabilen Button-Text "Take Photo" im camera_input-Widget. Der
    manuelle Button bleibt als Fallback sichtbar, falls der Auto-Klick
    (z.B. wegen einer künftigen Streamlit-Version) mal nicht greift.
    """
    st.components.v1.html(
        """
        <div id="autocap-status" style="font-family:sans-serif; font-size:1.3rem; font-weight:bold; color:white; background:red; padding:8px;">DEBUG v2 - Skript gestartet...</div>
        <script>
        (function() {
            const statusEl = document.getElementById('autocap-status');
            function setStatus(msg) { if (statusEl) { statusEl.textContent = msg; } }

            function simulateRealClick(el, win) {
                const rect = el.getBoundingClientRect();
                const x = rect.left + rect.width / 2;
                const y = rect.top + rect.height / 2;
                const base = { bubbles: true, cancelable: true, composed: true, clientX: x, clientY: y, view: win };
                ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(function(type) {
                    const Ctor = type.indexOf('pointer') === 0 ? win.PointerEvent : win.MouseEvent;
                    try {
                        el.dispatchEvent(new Ctor(type, base));
                    } catch (e) {
                        el.dispatchEvent(new win.MouseEvent(type, base));
                    }
                });
            }

            const candidates = ['take photo', 'take a photo', 'capture', 'foto aufnehmen', 'aufnehmen'];
            let attempts = 0;
            let clickedOnce = false;
            const maxAttempts = 150; // ca. 30s bei 200ms Intervall

            const interval = setInterval(function() {
                attempts++;
                try {
                    const buttons = window.parent.document.querySelectorAll('button');
                    const visible = Array.from(buttons).filter(function(b) {
                        return b.offsetWidth > 0 && b.offsetHeight > 0 && !b.disabled;
                    });
                    setStatus('Suche Auslöser... (Versuch ' + attempts + ', ' + visible.length + ' sichtbare Buttons)');
                    for (const btn of visible) {
                        const label = ((btn.innerText || '') + ' ' + (btn.getAttribute('aria-label') || '') + ' ' + (btn.title || ''))
                            .trim()
                            .toLowerCase();
                        if (candidates.some(function(c) { return label.includes(c); })) {
                            simulateRealClick(btn, window.parent);
                            clickedOnce = true;
                            setStatus('Auslöser geklickt (Versuch ' + attempts + '), warte auf Reaktion...');
                            clearInterval(interval);
                            return;
                        }
                    }
                } catch (e) {
                    setStatus('Fehler beim Zugriff auf die Seite: ' + e.message);
                    clearInterval(interval);
                    return;
                }
                if (attempts >= maxAttempts) {
                    setStatus(clickedOnce ? 'Geklickt, aber keine Reaktion erkannt.' : 'Auslöser nach ' + maxAttempts + ' Versuchen nicht gefunden.');
                    clearInterval(interval);
                }
            }, 200);
        })();
        </script>
        """,
        height=60,
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
