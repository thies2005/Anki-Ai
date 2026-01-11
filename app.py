import streamlit as st
import logging
from dotenv import load_dotenv

from components.session import init_session_state
from components.sidebar import render_sidebar
from components.generator import render_generator
from components.chat import render_pdf_chat, render_general_chat
from components.login import render_login
from components.onboarding import render_onboarding

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load env variables
load_dotenv()

# Versioning
VERSION = "v2.5.1"

# Page Config
st.set_page_config(
    page_title=f"Medical PDF to Anki {VERSION}",
    page_icon="🩺",
    layout="wide"
)

# Version Badge CSS
st.markdown(f"""
    <style>
    .version-badge {{
        position: fixed;
        top: 10px;
        left: 10px;
        background-color: rgba(0, 0, 0, 0.05);
        color: rgba(0, 0, 0, 0.5);
        padding: 4px 10px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: bold;
        z-index: 999999;
        pointer-events: none;
        font-family: 'Inter', sans-serif;
        border: 1px solid rgba(0, 0, 0, 0.1);
    }}
    [data-theme="dark"] .version-badge {{
        background-color: rgba(255, 255, 255, 0.1);
        color: rgba(255, 255, 255, 0.6);
        border: 1px solid rgba(255, 255, 255, 0.1);
    }}
    </style>
    <div class="version-badge">{VERSION}</div>
""", unsafe_allow_html=True)

# Title
st.title("🩺 Medical PDF to Anki Converter (AI-Powered)")

# Initialize Session
init_session_state()

# --- Auth Flow ---
if not st.session_state.get('is_logged_in', False):
    render_login()
    st.stop() # Stop execution here until logged in

# --- Onboarding Flow ---
# Check if keys are configured (either in session or environment)
# We consider "configured" if at least one provider key exists or user explicitly skipped.
if not st.session_state.get('keys_configured', False):
    # Check if we already have keys in user profile (loaded during login)
    user_keys = st.session_state.get('user_keys', {})
    if not user_keys:
         render_onboarding()
         st.stop()
    else:
        # We have keys, mark as configured
        st.session_state['keys_configured'] = True
        st.rerun()

# --- Main App ---

# Render Sidebar & Get Config
config = render_sidebar()

# Split View logic
st.divider()
if config["show_general_chat"]:
    col_gen, col_chat = st.columns([5, 4])
else:
    col_gen = st.container()
    col_chat = None

# 1. Generator Column
with col_gen:
    render_generator(config)

# 2. Chat Column (Optional)
if config["show_general_chat"] and col_chat is not None:
    with col_chat:
        render_general_chat(
            config["show_general_chat"], 
            config["provider"], 
            config["model_name"]
        )

# We need to render PDF Chat if chapters exist.
if 'chapters_data' in st.session_state and st.session_state['chapters_data']:
    with col_gen:
        st.divider()
        render_pdf_chat(
            st.session_state['chapters_data'], 
            config["provider"], 
            config["model_name"]
        )
