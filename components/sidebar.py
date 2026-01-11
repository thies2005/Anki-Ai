"""
Sidebar configuration component.
"""
import streamlit as st
import os
from utils.llm_handler import configure_gemini, configure_openrouter, configure_zai
from components.session import load_fallback_keys
from utils.auth import UserManager

def render_sidebar():
    """Renders the sidebar and returns configuration."""
    auth_manager = UserManager()
    email = st.session_state.get('user_email')
    user_keys = st.session_state.get('user_keys', {})

    with st.sidebar:
        st.header("Configuration")
        
        if email:
            st.caption(f"Logged in as: {email}")

        # Provider Selection
        provider = st.radio("AI Provider", ["Google Gemini", "OpenRouter", "Z.AI"], index=0)
        
        api_key = None
        model_name = None
        summary_model = None
        
        # Helper to check if key exists (saved or in env)
        def has_key(provider_key, env_var):
            return bool(user_keys.get(provider_key)) or bool(os.getenv(env_var))
        
        # --- Google Gemini ---
        if provider == "Google Gemini":
            fallback_keys = load_fallback_keys()
            saved_key = user_keys.get("google", "")
            env_key = os.getenv("GOOGLE_API_KEY", "")
            
            if saved_key:
                api_key = saved_key
                st.session_state.google_client = configure_gemini(api_key, fallback_keys=fallback_keys)
                st.success(f"✅ Gemini Key (saved)")
            elif env_key:
                api_key = env_key
                st.session_state.google_client = configure_gemini(api_key, fallback_keys=fallback_keys)
                st.info("Using Gemini Key from Environment")
            elif fallback_keys:
                api_key = fallback_keys[0]
                st.session_state.google_client = configure_gemini(api_key, fallback_keys=fallback_keys[1:])
                st.info("Using Fallback Gemini Key (Dev Mode)")
            else:
                st.error("No Gemini Keys found. Add one in ⚙️ API Key Settings below.")
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

        # --- OpenRouter ---
        elif provider == "OpenRouter": 
            saved_key = user_keys.get("openrouter", "")
            env_key = os.getenv("OPENROUTER_API_KEY", "")
            
            if saved_key:
                api_key = saved_key
                st.session_state.openrouter_client = configure_openrouter(api_key)
                st.success("✅ OpenRouter Key (saved)")
            elif env_key:
                api_key = env_key
                st.session_state.openrouter_client = configure_openrouter(api_key)
                st.info("Using OpenRouter Key from Environment")
            else:
                st.error("OpenRouter Key missing. Add one in ⚙️ API Key Settings below.")
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

        # --- Z.AI ---
        elif provider == "Z.AI":
            saved_key = user_keys.get("zai", "")
            env_key = os.getenv("ZAI_API_KEY", "")
            
            if saved_key:
                api_key = saved_key
                st.session_state.zai_client = configure_zai(api_key)
                st.success("✅ Z.AI Key (saved)")
            elif env_key:
                api_key = env_key
                st.session_state.zai_client = configure_zai(api_key)
                st.info("Using Z.AI Key from Environment")
            else:
                st.error("Z.AI Key missing. Add one in ⚙️ API Key Settings below.")
                api_key = None
                st.session_state.zai_client = configure_zai(None)
            
            model_options = {
                "GLM-4.7": "GLM-4.7 (Standard)",
                "GLM-4.5-air": "GLM-4.5 Air (Lightweight)"
            }
            summary_model = "GLM-4.7"
        
        # --- Model Selection ---
        selected_model_key = st.selectbox(
            "Model", 
            options=list(model_options.keys()), 
            format_func=lambda x: model_options[x],
            index=0
        )
        model_name = selected_model_key
        
        # --- API Key Settings Expander (for adding/changing keys) ---
        is_guest = st.session_state.get('is_guest', False)
        
        if not is_guest:
            with st.expander("⚙️ API Key Settings", expanded=False):
                st.caption("Add or update your API keys here. Keys are saved securely to your profile.")
                
                # Google
                st.markdown("[Get Gemini API Key](https://aistudio.google.com/app/api-keys)")
                new_google_key = st.text_input("Gemini API Key", value="", type="password", key="new_google_key", placeholder="Enter new key...")
                if new_google_key and st.button("💾 Save Gemini Key"):
                    auth_manager.save_keys(email, {"google": new_google_key})
                    st.session_state.user_keys["google"] = new_google_key
                    st.success("Gemini Key saved!")
                    st.rerun()
                
                st.divider()
                
                # OpenRouter
                st.markdown("[Get OpenRouter Key](https://openrouter.ai/keys)")
                new_openrouter_key = st.text_input("OpenRouter API Key", value="", type="password", key="new_openrouter_key", placeholder="Enter new key...")
                if new_openrouter_key and st.button("💾 Save OpenRouter Key"):
                    auth_manager.save_keys(email, {"openrouter": new_openrouter_key})
                    st.session_state.user_keys["openrouter"] = new_openrouter_key
                    st.success("OpenRouter Key saved!")
                    st.rerun()
                
                st.divider()
                
                # Z.AI
                st.markdown("[Get Z.AI API Key](https://z.ai/)")
                new_zai_key = st.text_input("Z.AI API Key", value="", type="password", key="new_zai_key", placeholder="Enter new key...")
                if new_zai_key and st.button("💾 Save Z.AI Key"):
                    auth_manager.save_keys(email, {"zai": new_zai_key})
                    st.session_state.user_keys["zai"] = new_zai_key
                    st.success("Z.AI Key saved!")
                    st.rerun()
        else:
            st.info("⚠️ Guest Mode: Keys are temporary. Log in to save keys.")

        st.divider()
        chunk_size = st.slider("Chunk Size (chars)", 5000, 20000, 10000, step=1000)
        developer_mode = st.toggle("Developer Mode", value=False)
        show_general_chat = st.toggle("Show General AI Chat", value=False, help="Enable the general AI chat panel on the right side")
        
        # History Toggle (Logged-in only)
        show_history = False
        if email and email != "Guest":
            show_history = st.toggle("📜 Show Card History", value=False, help="View and manage previously generated cards.")
        elif email == "Guest":
             st.caption("🔒 History disabled in Guest Mode")
        
        # AnkiConnect Configuration
        st.divider()
        with st.expander("🔗 AnkiConnect Settings", expanded=False):
            st.caption("For local use, keep default. For Cloud, use a tunnel.")
            anki_url = st.text_input(
                "AnkiConnect URL", 
                value=st.session_state.get('anki_connect_url') or os.getenv("ANKI_CONNECT_URL", "http://localhost:8765"),
                help="Default: http://localhost:8765"
            )
            # Store/Update in session
            st.session_state['anki_connect_url'] = anki_url
        
        st.divider()
        col_logout, col_clear = st.columns(2)
        with col_logout:
            if st.button("🚪 Logout"):
                st.session_state.clear()
                st.rerun()
        
        with col_clear:
             if st.button("🗑️ Reset"):
                # specific clear logic if we want to keep login? No, reset usually kills everything.
                st.session_state.clear()
                st.rerun()

    return {
        "provider": provider,
        "api_key": api_key,
        "model_name": model_name,
        "summary_model": summary_model,
        "chunk_size": chunk_size,
        "developer_mode": developer_mode,
        "show_general_chat": show_general_chat,
        "anki_url": anki_url,
        "show_history": show_history
    }
