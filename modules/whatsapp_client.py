"""WhatsApp-Versand via lokale Baileys-Bridge (bridge/server.js in Termux).

Konfiguration in .streamlit/secrets.toml:
    WHATSAPP_BRIDGE_URL    = "https://xyz.trycloudflare.com"
    WHATSAPP_BRIDGE_SECRET = "wonderbox"

Die Bridge läuft auf dem Smartphone in Termux und ist per Cloudflare-Tunnel
erreichbar. URL ändert sich bei jedem Neustart des Tunnels – dann secrets.toml
aktualisieren.
"""
import requests
import streamlit as st


def send_image(phone_number: str, image_url: str) -> tuple[bool, str | None]:
    """Schickt image_url als WhatsApp-Bild an phone_number (nur Ziffern, mit
    Ländervorwahl, z.B. '4915512345678'). Gibt (True, None) bei Erfolg zurück,
    (False, Fehlermeldung) bei Fehler."""
    bridge_url = st.secrets.get("WHATSAPP_BRIDGE_URL", "").rstrip("/")
    secret     = st.secrets.get("WHATSAPP_BRIDGE_SECRET", "wonderbox")

    if not bridge_url:
        return False, "WHATSAPP_BRIDGE_URL nicht konfiguriert (secrets.toml)"

    phone_digits = "".join(ch for ch in phone_number if ch.isdigit())
    if len(phone_digits) < 7:
        return False, "Ungültige Telefonnummer"

    try:
        resp = requests.post(
            f"{bridge_url}/send",
            json={"phone": phone_digits, "imageUrl": image_url},
            headers={"x-secret": secret},
            timeout=15,
        )
        resp.raise_for_status()
        return True, None
    except requests.RequestException as e:
        return False, str(e)
