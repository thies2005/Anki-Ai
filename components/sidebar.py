"""
Sidebar configuration component.
"""
import streamlit as st
import os
from utils.llm_handler import configure_gemini, configure_openrouter
from components.session import load_fallback_keys

def render_sidebar():
    """Renders the sidebar and returns configuration."""
    with st.sidebar:
        st.header("Configuration")
        
        # Provider Selection
        provider = st.radio("AI Provider", ["Google Gemini", "OpenRouter"], index=0)
        
        api_key = None
        model_name = None
        summary_model = None
        
        if provider == "Google Gemini":
            st.markdown("[Get Gemini API Key](https://aistudio.google.com/app/api-keys)")
            user_api_key = st.text_input("Gemini API Key", type="password", help="Leave empty to use built-in fallback keys.")
            
            fallback_keys = load_fallback_keys()
            
            # Init Google Client
            if user_api_key:
                api_key = user_api_key
                st.session_state.google_client = configure_gemini(api_key, fallback_keys=fallback_keys)
                st.success(f"Custom Gemini Key Configured! (+{len(fallback_keys)} backups)")
            else:
                if fallback_keys:
                    api_key = fallback_keys[0]
                    st.session_state.google_client = configure_gemini(api_key, fallback_keys=fallback_keys[1:])
                    st.info(f"Using Fallback Gemini Key (Dev Mode)")
                else:
                    st.error("No Gemini Keys found.")
                    api_key = None
                    st.session_state.google_client = configure_gemini(None, fallback_keys=[])
    
            # Google Models
            model_options = {
                "gemini-2.5-flash-lite": "Gemini 2.5 Flash Lite (Fastest, 10 RPM)",
                "gemini-2.5-flash": "Gemini 2.5 Flash (Standard, 5 RPM)",
                "gemini-3-flash": "Gemini 3.0 Flash (Smarter, 5 RPM)",
                "gemma-3-27b-it": "Gemma 3 27B (High Throughput, 30 RPM)"
            }
            summary_model = "gemma-3-27b-it" 
        
        else: # OpenRouter
            st.markdown("[Get OpenRouter Key](https://openrouter.ai/keys)")
            user_api_key = st.text_input("OpenRouter API Key", type="password")
            
            if user_api_key:
                api_key = user_api_key
                st.session_state.openrouter_client = configure_openrouter(api_key)
                st.success("OpenRouter Key Configured!")
            else:
                # Check env
                env_key = os.getenv("OPENROUTER_API_KEY")
                if env_key:
                    api_key = env_key
                    st.session_state.openrouter_client = configure_openrouter(api_key)
                    st.info("Using OpenRouter Key from Environment")
                else:
                    st.error("OpenRouter Key missing.")
                    api_key = None
                    st.session_state.openrouter_client = configure_openrouter(None)
    
            model_options = {
                "xiaomi/mimo-v2-flash:free": "Xiaomi Mimo V2 Flash (Free)",
                "google/gemini-2.0-flash-exp:free": "Gemini 2.0 Flash Exp (Free)",
                "mistralai/devstral-2512:free": "Mistral Devstral 2512 (Free)",
                "qwen/qwen3-coder:free": "Qwen 3 Coder (Free)",
                "google/gemma-3-27b-it:free": "Gemma 3 27B IT (Free)"
            }
            summary_model = "google/gemini-2.0-flash-exp:free"
        
        selected_model_key = st.selectbox(
            "Model", 
            options=list(model_options.keys()), 
            format_func=lambda x: model_options[x],
            index=0
        )
        model_name = selected_model_key
        
        st.divider()
        chunk_size = st.slider("Chunk Size (chars)", 5000, 20000, 10000, step=1000)
        developer_mode = st.toggle("Developer Mode", value=False)
        show_general_chat = st.toggle("Show General AI Chat", value=False, help="Enable the general AI chat panel on the right side")
        
        st.divider()
        if st.button("🔒 Clear Session & Keys", type="secondary"):
            st.session_state.clear()
            st.rerun()

    return {
        "provider": provider,
        "api_key": api_key,
        "model_name": model_name,
        "summary_model": summary_model,
        "chunk_size": chunk_size,
        "developer_mode": developer_mode,
        "show_general_chat": show_general_chat
    }
