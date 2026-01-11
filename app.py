import streamlit as st
import logging
from dotenv import load_dotenv

from components.session import init_session_state
from components.sidebar import render_sidebar
from components.generator import render_generator
from components.chat import render_pdf_chat, render_general_chat

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

# Render Sidebar & Get Config
config = render_sidebar()

# Split View
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
else:
    # If using split view logic inside components/chat.py but we want 
    # specific placement. 
    # Actually, the split view logic in original app had
    # Chat with PDF inside the generator column (bottom) 
    # AND General Chat in the right column.
    
    # render_pdf_chat needs creation inside generator flow?
    # In original app, 'Chat with PDF' was under 'chapters_data' loop inside col_gen.
    # In my component split:
    # Generator handles generated content.
    # Chat handles interaction.
    
    # We should render PDF chat inside the Generator column if chapters exist.
    # But `render_generator` encapsulates that logic?
    # Let's check `components/generator.py` I just wrote.
    # I didn't include `render_pdf_chat` inside `render_generator`.
    # Let's add it here, or inside generator.
    pass

# We need to render PDF Chat if chapters exist.
if 'chapters_data' in st.session_state and st.session_state['chapters_data']:
    with col_gen:
        st.divider()
        render_pdf_chat(
            st.session_state['chapters_data'], 
            config["provider"], 
            config["model_name"]
        )
