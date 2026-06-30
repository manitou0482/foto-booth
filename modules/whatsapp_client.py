"""WhatsApp-Versand via Green API.

Konfiguration in .streamlit/secrets.toml:
    GREEN_API_INSTANCE_ID = "1234567890"
    GREEN_API_TOKEN       = "abcdef1234567890abcdef"

Kostenloses Konto: https://green-api.com
Free-Tier: 500 Nachrichten/Monat.
Setup: Konto anlegen → Instanz erstellen → eigene WhatsApp-Nummer per QR-Code verbinden.
"""
import requests
import streamlit as st


def send_image(phone_number: str, image_url: str) -> tuple[bool, str | None]:
    """Sendet das Bild als WhatsApp-Nachricht an phone_number (nur Ziffern, mit
    Ländervorwahl, z.B. '4915512345678'). Gibt (True, None) bei Erfolg zurück,
    (False, Fehlermeldung) bei Fehler."""
    instance_id = st.secrets.get("GREEN_API_INSTANCE_ID")
    api_token = st.secrets.get("GREEN_API_TOKEN")

    if not instance_id or not api_token:
        return False, "GREEN_API nicht konfiguriert (secrets.toml)"

    phone_digits = "".join(ch for ch in phone_number if ch.isdigit())
    if len(phone_digits) < 7:
        return False, "Ungültige Telefonnummer"

    chat_id = f"{phone_digits}@c.us"
    url = (
        f"https://api.green-api.com"
        f"/waInstance{instance_id}/sendFileByUrl/{api_token}"
    )
    payload = {
        "chatId": chat_id,
        "urlFile": image_url,
        "fileName": "wonderbox_foto.jpg",
        "caption": "Dein Wonderbox-Foto! ✨",
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        return True, None
    except requests.RequestException as e:
        return False, str(e)
