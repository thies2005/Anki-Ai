import streamlit as st
from utils.auth import UserManager
import time

def render_login():
    """Renders the login, registration, and password reset tabs."""
    st.header("🔐 Welcome to Anki AI")
    
    # Session state for reset flow
    if 'reset_stage' not in st.session_state:
        st.session_state['reset_stage'] = 'email' # email or verify
    
    tab_login, tab_register, tab_reset = st.tabs(["Login", "Register", "Forgot Password"])
    
    auth_manager = UserManager()

    # --- Login ---
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
                        # Reset is_guest if accidentally set
                        st.session_state['is_guest'] = False
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error(result)

    # --- Register ---
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
                        st.success(f"{msg} Welcome email sent!")
                        st.info("Please switch to the Login tab to sign in.")
                    else:
                        st.error(msg)
    
    # --- Password Reset ---
    with tab_reset:
        st.caption("Reset your password via email verification.")
        
        if st.session_state['reset_stage'] == 'email':
            with st.form("reset_request_form"):
                reset_email = st.text_input("Enter your registered Email")
                submit_req = st.form_submit_button("Send Verification Code")
                
                if submit_req:
                    if not reset_email:
                        st.error("Email required.")
                    else:
                        success, msg = auth_manager.initiate_password_reset(reset_email)
                        if success:
                            st.success(msg)
                            st.session_state['reset_email'] = reset_email
                            st.session_state['reset_stage'] = 'verify'
                            st.rerun()
                        else:
                            st.error(msg)
        
        elif st.session_state['reset_stage'] == 'verify':
            st.info(f"Code sent to {st.session_state.get('reset_email')}")
            with st.form("reset_verify_form"):
                code = st.text_input("Verification Code", max_chars=6)
                new_pass = st.text_input("New Password", type="password")
                confirm_pass = st.text_input("Confirm New Password", type="password")
                submit_verify = st.form_submit_button("Reset Password")
                
                if submit_verify:
                    if new_pass != confirm_pass:
                        st.error("Passwords do not match.")
                    else:
                        email = st.session_state.get('reset_email')
                        success, msg = auth_manager.complete_password_reset(email, code, new_pass)
                        if success:
                            st.success(msg)
                            st.session_state['reset_stage'] = 'email'
                            time.sleep(2)
                            st.rerun()
                        else:
                            st.error(msg)
            
            if st.button("Back"):
                st.session_state['reset_stage'] = 'email'
                st.rerun()

    
    st.markdown("---")
    if st.button("👤 Continue as Guest"):
        st.session_state['is_logged_in'] = True
        st.session_state['user_email'] = "Guest"
        st.session_state['is_guest'] = True
        st.session_state['user_keys'] = {} # No saved keys for guest
        st.rerun()
