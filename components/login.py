import streamlit as st
from utils.auth import UserManager
import time

def render_login():
    """Renders the login and registration tabs."""
    st.header("🔐 Welcome to Anki AI")
    
    tab_login, tab_register = st.tabs(["Login", "Register"])
    
    auth_manager = UserManager()

    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Login")
            
            if submit:
                if not email or not password:
                    st.error("Please enter both email and password.")
                else:
                    success, result = auth_manager.login(email, password)
                    if success:
                        st.success("Login successful!")
                        # Update session state
                        st.session_state['is_logged_in'] = True
                        st.session_state['user_email'] = result['email']
                        st.session_state['user_keys'] = result['api_keys']
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error(result)

    with tab_register:
        with st.form("register_form"):
            new_email = st.text_input("Email")
            new_password = st.text_input("Password", type="password")
            confirm_password = st.text_input("Confirm Password", type="password")
            submit_reg = st.form_submit_button("Register")
            
            if submit_reg:
                if not new_email or not new_password:
                    st.error("Please fill in all fields.")
                elif new_password != confirm_password:
                    st.error("Passwords do not match.")
                else:
                    success, msg = auth_manager.register(new_email, new_password)
                    if success:
                        st.success(msg)
                        st.info("Please switch to the Login tab to sign in.")
                    else:
                        st.error(msg)
    
    st.markdown("---")
    if st.button("👤 Continue as Guest"):
        st.session_state['is_logged_in'] = True
        st.session_state['user_email'] = "Guest"
        st.session_state['is_guest'] = True
        st.session_state['user_keys'] = {} # No saved keys for guest
        st.rerun()
