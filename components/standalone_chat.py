"""
Standalone Chat component with full-screen view, model selector, and file upload.
"""
import streamlit as st
from utils.llm_handler import get_chat_response, configure_gemini, configure_openrouter, configure_zai
from utils.pdf_processor import extract_text_from_pdf
import os
import logging

logger = logging.getLogger(__name__)

# Constants
MAX_FILE_SIZE_MB = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# Allowed MIME types for security
ALLOWED_MIME_TYPES = {
    '.pdf': 'application/pdf',
    '.txt': 'text/plain',
    '.md': 'text/markdown',
}

# File signature validation (magic bytes)
PDF_MAGIC = b'%PDF'
TEXT_EXTENSIONS = {'.txt', '.md'}

def validate_file_security(file, fname: str) -> tuple[bool, str]:
    """
    Validate file security checks: size, extension, and content signature.
    Returns: (is_valid, error_message)
    """
    # Check file size
    if file.size > MAX_FILE_SIZE_BYTES:
        return False, f"File exceeds {MAX_FILE_SIZE_MB}MB limit"

    # Check file extension
    file_ext = os.path.splitext(fname)[1].lower()
    if file_ext not in ALLOWED_MIME_TYPES:
        return False, f"Invalid file type: {file_ext}"

    # For PDFs, validate magic bytes
    if file_ext == '.pdf':
        file.seek(0)
        header = file.read(4)
        file.seek(0)
        if not header.startswith(PDF_MAGIC):
            return False, "Invalid PDF file (magic bytes check failed)"

    return True, ""

def sanitize_text_content(text: str, max_length: int = 5000000) -> str:
    """
    Sanitize text content to prevent injection attacks.
    Limits length and removes potentially dangerous content.
    """
    if not text:
        return ""

    # Limit total length to prevent DoS
    if len(text) > max_length:
        text = text[:max_length] + "\n\n[Content truncated due to length]"

    return text

def render_standalone_chat():
    """Renders the full standalone chat interface with model selector and upload."""
    
    # Custom CSS for chat layout
    st.markdown("""
    <style>
    .chat-controls {
        display: flex;
        gap: 10px;
        align-items: center;
        background: rgba(255, 255, 255, 0.05);
        padding: 10px;
        border-radius: 12px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        margin-bottom: 20px;
    }
    .stChatMessage {
        background: transparent !important;
    }
    </style>
    """, unsafe_allow_html=True)
    
    st.markdown("## 💬 AI Chat")
    
    # --- Top Control Bar ---
    col_back, col_model, col_files, col_actions = st.columns([1, 2, 2, 1])
    
    with col_back:
        # Back functionality is handled by global header
        st.write("") 

    with col_model:
        with st.popover("⚙️ Model Settings", use_container_width=True):
            st.markdown("##### AI Provider")
            
            # Use defaults from settings
            providers = ["Google Gemini", "OpenRouter", "Z.AI"]
            default_provider = st.session_state.get('default_provider', 'Google Gemini')
            default_idx = providers.index(default_provider) if default_provider in providers else 0
            
            chat_provider = st.radio(
                "Provider",
                providers,
                index=default_idx,
                key="chat_provider_select"
            )
            
            # Model Selection logic
            if chat_provider == "Google Gemini":
                model_options = {
                    "gemini-2.5-flash-lite": "Flash Lite (Fast)",
                    "gemini-2.5-flash": "Flash (Standard)",
                    "gemini-3-flash": "Flash 3.0 (Smart)",
                    "gemma-3-27b-it": "Gemma 3 27B"
                }
            elif chat_provider == "OpenRouter":
                model_options = {
                    "xiaomi/mimo-v2-flash:free": "Mimo V2 Flash",
                    "google/gemini-2.0-flash-exp:free": "Gemini 2.0 Flash",
                    "mistralai/devstral-2512:free": "Mistral",
                    "qwen/qwen3-coder:free": "Qwen 3 Coder",
                    "google/gemma-3-27b-it:free": "Gemma 3 27B"
                }
            else:  # Z.AI
                model_options = {
                    "GLM-4.7": "GLM-4.7",
                    "GLM-4.5-air": "GLM-4.5 Air"
                }
            
            model_keys = list(model_options.keys())
            default_model = st.session_state.get('default_model', model_keys[0])
            default_model_idx = model_keys.index(default_model) if default_model in model_keys else 0
            
            chat_model = st.selectbox(
                "Model",
                options=model_keys,
                format_func=lambda x: model_options[x],
                index=default_model_idx,
                key="chat_model_select"
            )

    with col_files:
        # Check if we have context
        has_context = bool(st.session_state.get('chat_context', ''))
        label = "📎 Context (Active)" if has_context else "📎 Add Files"
        btn_type = "primary" if has_context else "secondary"
        
        with st.popover(label, use_container_width=True):
            st.markdown(f"### Upload Context (Max {MAX_FILE_SIZE_MB}MB/file)")
            uploaded_files = st.file_uploader(
                f"Drag & drop PDF/TXT/MD files (Max {MAX_FILE_SIZE_MB}MB/file)",
                type=["pdf", "txt", "md"],
                accept_multiple_files=True,
                key="chat_file_upload",
                help=f"Individual files must be under {MAX_FILE_SIZE_MB}MB."
            )
            
            # Validate file sizes
            valid_files = []
            if uploaded_files:
                for f in uploaded_files:
                    # Validate file security
                    is_valid, error_msg = validate_file_security(f, f.name)
                    if not is_valid:
                        st.warning(f"⚠️ {f.name}: {error_msg}")
                    else:
                        valid_files.append(f)
                uploaded_files = valid_files

            if st.button("🗑️ Clear Context", key="clear_context_pop"):
                st.session_state.chat_context = ""
                st.rerun()

            # Process files
            if uploaded_files:
                if 'processed_files_cache' not in st.session_state:
                    st.session_state.processed_files_cache = set()

                context_texts = []
                for file in uploaded_files:
                    file.seek(0)
                    fname = file.name
                    file_ext = os.path.splitext(fname)[1].lower()
                    try:
                        if file_ext == '.pdf':
                            text = extract_text_from_pdf(file)
                        else:
                            text = file.read().decode('utf-8', errors='replace')

                        # Sanitize text content
                        text = sanitize_text_content(text)
                        if not text.strip():
                            st.warning(f"⚠️ {fname}: No content extracted")
                            continue

                        context_texts.append(f"[{fname}]\n{text}")
                    except UnicodeDecodeError:
                        st.error(f"Error {fname}: Unable to decode file content. Please ensure it's a valid text file.")
                    except Exception as e:
                        logger.error(f"Error processing file {fname}: {e}")
                        st.error(f"Error {fname}: Failed to process file")

                if context_texts:
                    st.session_state.chat_context = "\n\n---\n\n".join(context_texts)
                    st.success(f"✅ {len(context_texts)} files active")

    with col_actions:
        if st.button("🗑️", help="Clear History", key="clear_hist_btn", use_container_width=True):
            st.session_state.standalone_messages = []
            st.rerun()

    st.divider()

    # --- Chat Area ---
    if "standalone_messages" not in st.session_state:
        st.session_state.standalone_messages = []
    
    # Calculate container height based on screen (approx)
    chat_container = st.container(height=600)
    
    with chat_container:
        if not st.session_state.standalone_messages:
            st.markdown("""
            <div style="text-align: center; padding: 4rem; opacity: 0.5;">
                <h1>💬</h1>
                <h3>Start chatting</h3>
                <p>Configure model and add files from the top bar.</p>
            </div>
            """, unsafe_allow_html=True)
        else:
            for message in st.session_state.standalone_messages:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])
    
    # --- Input ---
    if prompt := st.chat_input("Message Anki AI...", key="standalone_chat_input"):
        # Add user message
        st.session_state.standalone_messages.append({"role": "user", "content": prompt})
        
        # Get provider code
        provider_code = "google" if chat_provider == "Google Gemini" else ("zai" if chat_provider == "Z.AI" else "openrouter")
        
        # Configure client logic
        user_keys = st.session_state.get('user_keys', {})
        
        # Ensure client is ready (simple lazy init)
        if provider_code == "google":
            key = user_keys.get("google") or os.getenv("GOOGLE_API_KEY")
            if not st.session_state.get('google_client'):
                st.session_state.google_client = configure_gemini(key)
        elif provider_code == "openrouter":
            key = user_keys.get("openrouter") or os.getenv("OPENROUTER_API_KEY")
            if not st.session_state.get('openrouter_client'):
                st.session_state.openrouter_client = configure_openrouter(key)
        else: # zai
            key = user_keys.get("zai") or os.getenv("ZAI_API_KEY")
            if not st.session_state.get('zai_client'):
                st.session_state.zai_client = configure_zai(key)
        
        with chat_container:
            with st.chat_message("user"):
                st.markdown(prompt)
            
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    context = st.session_state.get('chat_context', "")
                    response = get_chat_response(
                        st.session_state.standalone_messages,
                        context,
                        provider_code,
                        chat_model,
                        google_client=st.session_state.get('google_client'),
                        openrouter_client=st.session_state.get('openrouter_client'),
                        zai_client=st.session_state.get('zai_client'),
                        direct_chat=not bool(context)
                    )
                st.markdown(response)
        
        st.session_state.standalone_messages.append({"role": "assistant", "content": response})
        st.rerun()
