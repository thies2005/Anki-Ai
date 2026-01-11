"""
Session state management for Anki AI.
"""
import streamlit as st
import os

def init_session_state():
    """Initialize all session state variables."""
    defaults = {
        "google_client": None,
        "openrouter_client": None,
        "zai_client": None,
        # NOTE: Do NOT set "anki_uploader" here - it's managed by st.file_uploader widget
        "chapters_data": [],
        "generated_questions": [],
        "pdf_messages": [],
        "general_messages": [],
        "vector_store": None,
        # Auth
        "is_logged_in": False,
        "user_email": None,
        "user_keys": {},
        "keys_configured": False
    }
    
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

def load_fallback_keys() -> list[str]:
    """Load fallback keys from environment variables."""
    keys = []
    for i in range(1, 11):
        key = os.getenv(f"FALLBACK_KEY_{i}")
        if key and key.strip():
            keys.append(key.strip())
    return keys
