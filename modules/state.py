"""Geteilter Zustand für den Zwei-Geräte-Modus.

st.cache_resource liefert allen Sessions derselben laufenden App-Instanz
dasselbe BoothState-Objekt zurück. Das funktioniert ohne externe Datenbank,
solange die App-Instanz nicht neu startet (z.B. nach Schlaf-Modus auf
Streamlit Community Cloud bei Inaktivität).
"""
import streamlit as st
from dataclasses import dataclass, field
import threading


@dataclass
class BoothState:
    phase: str = "idle"  # idle -> theme_selected -> countdown -> captured_ready -> processing -> result
    theme_id: str | None = None
    capture_token: str = "none"
    captured_image_bytes: bytes | None = None
    result_image_url: str | None = None
    error: str | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)

    def reset(self):
        with self.lock:
            self.phase = "idle"
            self.theme_id = None
            self.capture_token = "none"
            self.captured_image_bytes = None
            self.result_image_url = None
            self.error = None


@dataclass
class AdminSettings:
    """Globale Admin-Einstellungen - gelten für alle Sessions/Geräte gleich,
    unabhängig vom gewählten Aufbau (1 oder 2 Geräte), da die physische
    Kamera-Hardware sich nicht pro Gast ändert."""
    camera_facing: str = "environment"  # "environment" = Rückkamera, "user" = Frontkamera


@st.cache_resource
def get_admin_settings() -> AdminSettings:
    return AdminSettings()


@st.cache_resource
def get_shared_state() -> BoothState:
    return BoothState()


def get_session_state() -> BoothState:
    """Eigener, nicht geteilter Zustand pro Browser-Session - für Modus 1
    (All-in-One), damit parallele Gäste sich nicht gegenseitig stören."""
    if "booth_state" not in st.session_state:
        st.session_state.booth_state = BoothState()
    return st.session_state.booth_state
