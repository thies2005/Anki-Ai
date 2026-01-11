import streamlit as st
from utils.auth import UserManager

def render_onboarding():
    """Renders the onboarding screen for setting up API keys."""
    st.header("👋 Getting Started")
    st.write("To use Anki AI, you need to configure at least one AI Provider.")
    st.markdown("---")

    auth_manager = UserManager()
    email = st.session_state.get('user_email')
    
    # Pre-fill with existing keys if any (partial setup)
    current_keys = st.session_state.get('user_keys', {})

    with st.form("onboarding_form"):
        st.subheader("API Keys (Optional - fill at least one)")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### Google Gemini")
            st.markdown("[Get Key](https://aistudio.google.com/app/api-keys)")
            gemini_key = st.text_input("Gemini API Key", value=current_keys.get("google", ""), type="password")
            
            st.markdown("### Z.AI")
            st.markdown("[Get Key](https://z.ai/)")
            zai_key = st.text_input("Z.AI API Key", value=current_keys.get("zai", ""), type="password")

        with col2:
            st.markdown("### OpenRouter")
            st.markdown("[Get Key](https://openrouter.ai/keys)")
            openrouter_key = st.text_input("OpenRouter API Key", value=current_keys.get("openrouter", ""), type="password")

        st.markdown("---")
        submit = st.form_submit_button("Save & Continue")
        
        if submit:
            new_keys = {}
            if gemini_key: new_keys["google"] = gemini_key
            if zai_key: new_keys["zai"] = zai_key
            if openrouter_key: new_keys["openrouter"] = openrouter_key
            
            if not new_keys:
                st.warning("Please provide at least one API key to proceed.")
            else:
                # Save to disk
                auth_manager.save_keys(email, new_keys)
                
                # Update session
                st.session_state['user_keys'] = new_keys
                st.session_state['keys_configured'] = True
                
                st.success("Setup complete! Redirecting...")
                st.rerun()

    if st.button("Skip for now (Limited Functionality)"):
        st.session_state['keys_configured'] = True
        st.rerun()
