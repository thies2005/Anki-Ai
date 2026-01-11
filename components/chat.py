"""
Chat component for PDF interaction.
"""
import streamlit as st
from utils.llm_handler import get_chat_response

def render_pdf_chat(chapters_data, provider, model_name):
    """Renders the PDF chat interface."""
    with st.expander("💬 Chat with PDF", expanded=False):
        all_text_context = "\n\n".join([c['text'] for c in chapters_data])
        st.caption(f"Context: {len(chapters_data)} files loaded.")
        
        if "pdf_messages" not in st.session_state:
            st.session_state.pdf_messages = []

        pdf_chat_container = st.container(height=400)
        with pdf_chat_container:
            for message in st.session_state.pdf_messages:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])

        if pdf_prompt := st.chat_input("Ask about the PDFs...", key="pdf_chat_input"):
            st.session_state.pdf_messages.append({"role": "user", "content": pdf_prompt})
            with pdf_chat_container:
                with st.chat_message("user"):
                    st.markdown(pdf_prompt)

                with st.chat_message("assistant"):
                    provider_code = "google" if provider == "Google Gemini" else ("zai" if provider == "Z.AI" else "openrouter")
                    with st.spinner("Thinking (RAG)..."):
                        # RAG Retrieval
                        context_text = ""
                        if 'vector_store' in st.session_state and st.session_state.vector_store:
                            relevant_chunks = st.session_state.vector_store.search(pdf_prompt, google_client=st.session_state.google_client, k=5)
                            context_text = "\n\n".join([c['text'] for c in relevant_chunks])
                        else:
                            # Fallback
                            context_text = all_text_context[:100000]

                        response = get_chat_response(
                            st.session_state.pdf_messages, 
                            context_text, 
                            provider_code, 
                            model_name,
                            google_client=st.session_state.google_client,
                            openrouter_client=st.session_state.openrouter_client,
                            zai_client=st.session_state.zai_client,
                            direct_chat=False
                        )
                    st.markdown(response)
            
            st.session_state.pdf_messages.append({"role": "assistant", "content": response})
            st.rerun()

def render_general_chat(show_general_chat, provider, model_name):
    """Renders the general AI chat interface."""
    if show_general_chat:
        st.subheader("🤖 General AI Chat")
        st.caption(f"Model: {model_name}")
        
        if "general_messages" not in st.session_state:
            st.session_state.general_messages = []

        gen_chat_container = st.container(height=600)
        with gen_chat_container:
            for message in st.session_state.general_messages:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])

        if gen_prompt := st.chat_input("Chat with the AI...", key="general_chat_input"):
            st.session_state.general_messages.append({"role": "user", "content": gen_prompt})
            with gen_chat_container:
                with st.chat_message("user"):
                    st.markdown(gen_prompt)

                with st.chat_message("assistant"):
                    provider_code = "google" if provider == "Google Gemini" else ("zai" if provider == "Z.AI" else "openrouter")
                    with st.spinner("Thinking..."):
                        response = get_chat_response(
                            st.session_state.general_messages, 
                            "",  # No context for general chat
                            provider_code, 
                            model_name,
                            google_client=st.session_state.google_client,
                            openrouter_client=st.session_state.openrouter_client,
                            zai_client=st.session_state.zai_client,
                            direct_chat=True
                        )
                    st.markdown(response)
            
            st.session_state.general_messages.append({"role": "assistant", "content": response})
            st.rerun()
