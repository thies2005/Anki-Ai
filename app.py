import streamlit as st
import pandas as pd
from io import StringIO
import os
from dotenv import load_dotenv

load_dotenv()
from utils.pdf_processor import extract_text_from_pdf, clean_text, recursive_character_text_splitter
from utils.llm_handler import configure_gemini, configure_openrouter, process_chunk, get_chat_response, sort_files_with_gemini, generate_chapter_summary, generate_full_summary

# Page Config
st.set_page_config(
    page_title="Medical PDF to Anki",
    page_icon="🩺",
    layout="wide"
)

# Title
st.title("🩺 Medical PDF to Anki Converter (AI-Powered)")

# Sidebar: Config
with st.sidebar:
    st.header("Configuration")
    
    # Provider Selection
    provider = st.radio("AI Provider", ["Google Gemini", "OpenRouter"], index=0)
    
    api_key = None
    
    if provider == "Google Gemini":
        st.markdown("[Get Gemini API Key](https://aistudio.google.com/app/api-keys)")
        user_api_key = st.text_input("Gemini API Key", type="password", help="Leave empty to use built-in fallback keys.")
        
        # Load Fallback Keys
        fallback_keys = []
        for i in range(1, 11):
            key = os.getenv(f"FALLBACK_KEY_{i}")
            if key and key.strip():
                fallback_keys.append(key.strip())
        
        # Init Google Client
        if user_api_key:
            api_key = user_api_key
            configure_gemini(api_key, fallback_keys=fallback_keys)
            st.success(f"Custom Gemini Key Configured! (+{len(fallback_keys)} backups)")
        else:
            if fallback_keys:
                api_key = fallback_keys[0]
                configure_gemini(api_key, fallback_keys=fallback_keys[1:])
                st.info(f"Using Fallback Gemini Key (Dev Mode)")
            else:
                st.error("No Gemini Keys found.")
                api_key = None
                configure_gemini(None, fallback_keys=[])

        # Google Models
        model_options = {
            "gemini-2.5-flash-lite": "Gemini 2.5 Flash Lite (Fastest, 10 RPM)",
            "gemini-2.5-flash": "Gemini 2.5 Flash (Standard, 5 RPM)",
            "gemini-3-flash": "Gemini 3.0 Flash (Smarter, 5 RPM)",
            "gemma-3-27b-it": "Gemma 3 27B (High Throughput, 30 RPM)"
        }
        summary_model = "gemma-3-27b-it" # For Google: use Gemma
    
    else: # OpenRouter
        st.markdown("[Get OpenRouter Key](https://openrouter.ai/keys)")
        user_api_key = st.text_input("OpenRouter API Key", type="password")
        
        if user_api_key:
            api_key = user_api_key
            configure_openrouter(api_key)
            st.success("OpenRouter Key Configured!")
        else:
            # Check env
            env_key = os.getenv("OPENROUTER_API_KEY")
            if env_key:
                api_key = env_key
                configure_openrouter(api_key)
                st.info("Using OpenRouter Key from Environment")
            else:
                st.error("OpenRouter Key missing.")
                api_key = None
                configure_openrouter(None)

        model_options = {
            "xiaomi/mimo-v2-flash:free": "Xiaomi Mimo V2 Flash (Free)",
            "google/gemini-2.0-flash-exp:free": "Gemini 2.0 Flash Exp (Free)",
            "mistralai/devstral-2512:free": "Mistral Devstral 2512 (Free)",
            "qwen/qwen3-coder:free": "Qwen 3 Coder (Free)",
            "google/gemma-3-27b-it:free": "Gemma 3 27B IT (Free)"
        }
        summary_model = "google/gemini-2.0-flash-exp:free" # For OpenRouter: use Gemini 2.0 Free
    
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

# Split View
st.divider()
col_gen, col_chat = st.columns([5, 4])

# ==================== ANKI GENERATOR COLUMN ====================
with col_gen:
    st.subheader("1. Card Generator")
    
    with st.expander("Formatting Options", expanded=False):
        card_length = st.select_slider("Answer Length", options=["Short (1-2 words)", "Medium (Standard)", "Long (Conceptual)"], value="Medium (Standard)")
        card_density = st.select_slider("Card Count / Density", options=["Low (Key Concepts)", "Normal", "High (Comprehensive)"], value="Normal")
        enable_highlighting = st.toggle("Highlight Key Terms (Bold)", value=True)
        custom_prompt = st.text_area("Custom Instructions", help="E.g., 'Focus on Pharmacology'")
        deck_type = st.radio("Deck Organization", ["Subdecks (Medical::Item)", "Tags Only (Deck: Medical, Tag: Item)", "Both"], help="Organization structure.")

    uploaded_files = st.file_uploader("Upload Medical PDF(s)", type=["pdf"], accept_multiple_files=True, key="anki_uploader")

    if uploaded_files and api_key:
        # Processing Logic
        if st.button("Process Files & Generate Summaries", type="secondary"):
             with st.spinner("Processing files..."):
                file_map = {f.name: f for f in uploaded_files}
                sorted_names = list(file_map.keys())
                
                file_chapters = []
                progress_text = st.empty()
                
                for idx, name in enumerate(sorted_names):
                    if name in file_map:
                        progress_text.text(f"Extracting text from {name}...")
                        f = file_map[name]
                        text = extract_text_from_pdf(f)
                        fname = f.name.replace(".pdf", "").replace("_", " ").title()
                        
                        # Generate Summary
                        progress_text.text(f"Summarizing {name}...")
                        try:
                            summary = generate_chapter_summary(text, model_name=summary_model)
                        except:
                            summary = "(Summary generation failed)"
                        
                        file_chapters.append({
                            "title": fname,
                            "text": text,
                            "summary": summary
                        })
                
                st.session_state['chapters_data'] = file_chapters
                st.toast(f"Processed {len(file_chapters)} files", icon="📚")
        
        # Show Data & Generate
        if 'chapters_data' in st.session_state and st.session_state['chapters_data']:
            st.divider()
            
            # Document Summary
            with st.expander("📄 Document Summary", expanded=True):
                for ch in st.session_state['chapters_data']:
                    st.markdown(f"**{ch['title']}:** {ch['summary']}")
            
            # Chat with PDF (document-context)
            with st.expander("💬 Chat with PDF", expanded=False):
                all_text_context = "\n\n".join([c['text'] for c in st.session_state['chapters_data']])
                st.caption(f"Context: {len(st.session_state['chapters_data'])} files loaded.")
                
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
                            provider_code = "google" if provider == "Google Gemini" else "openrouter"
                            with st.spinner("Thinking..."):
                                response = get_chat_response(
                                    st.session_state.pdf_messages, 
                                    all_text_context, 
                                    provider_code, 
                                    model_name,
                                    direct_chat=False
                                )
                            st.markdown(response)
                    
                    st.session_state.pdf_messages.append({"role": "assistant", "content": response})
                    st.rerun()
            
            st.divider()

            # Global Gen Button
            if st.button("⚡ Generate All Anki Cards", type="primary"):
                try:
                    total_chapters = len(st.session_state['chapters_data'])
                    all_dfs = []
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    provider_code = "google" if provider == "Google Gemini" else "openrouter"
                    
                    for ch_idx, chapter in enumerate(st.session_state['chapters_data']):
                        raw_text = chapter['text']
                        cleaned = clean_text(raw_text)
                        chunks = recursive_character_text_splitter(cleaned, chunk_size=chunk_size)
                        
                        status_text.text(f"Processing {chapter['title']}...")
                        
                        for chunk_idx, chunk in enumerate(chunks):
                            current_progress = (ch_idx + (chunk_idx / len(chunks))) / total_chapters
                            progress_bar.progress(min(current_progress, 1.0))
                            
                            csv_chunk = process_chunk(
                                chunk, 
                                provider=provider_code,
                                model_name=model_name,
                                card_length=card_length,
                                card_density=card_density,
                                enable_highlighting=enable_highlighting,
                                custom_prompt=custom_prompt
                            )
                            
                            if csv_chunk and not csv_chunk.startswith("Error"):
                                try:
                                    df_chunk = pd.read_csv(StringIO(csv_chunk), sep="|", names=["Front", "Back"], engine="python", quotechar='"', on_bad_lines='skip')
                                    clean_title = chapter['title'].replace(" ", "_").replace(":", "-")
                                    if "Subdecks" in deck_type:
                                        df_chunk["Deck"] = f"Medical::{clean_title}"
                                        df_chunk["Tag"] = ""
                                    elif "Tags" in deck_type:
                                         df_chunk["Deck"] = "Medical"
                                         df_chunk["Tag"] = clean_title
                                    else:
                                         df_chunk["Deck"] = f"Medical::{clean_title}"
                                         df_chunk["Tag"] = clean_title
                                    all_dfs.append(df_chunk)
                                except: pass
                    
                    progress_bar.progress(1.0)
                    if all_dfs:
                        final_df = pd.concat(all_dfs, ignore_index=True)
                        final_df = final_df[["Front", "Back", "Deck", "Tag"]]
                        st.session_state['result_df'] = final_df
                        st.session_state['result_csv'] = final_df.to_csv(sep="|", index=False, header=False, quoting=1)
                        st.success(f"Generated {len(final_df)} cards!")
                    else:
                        st.error("No cards generated. Check errors above.")
                except Exception as e:
                    st.error(f"Error: {e}")

            if 'result_df' in st.session_state:
                st.dataframe(st.session_state['result_df'], width='stretch')
                st.download_button("Download .csv", st.session_state['result_csv'], "anki_cards.csv", "text/csv")
            
            st.divider()
            
            # Individual Chapter Expanders with Single-Gen Button
            for idx, ch in enumerate(st.session_state['chapters_data']):
                with st.expander(f"📁 {ch['title']}", expanded=False):
                    new_title = st.text_input(f"Title", value=ch['title'], key=f"title_{idx}")
                    st.caption(f"Summary: {ch['summary']}")
                    st.text_area(f"Content Preview", value=ch['text'][:500]+"...", disabled=True, height=100)
                    
                    # Single Chapter Generation
                    if st.button(f"⚡ Generate Cards for this Chapter", key=f"gen_single_{idx}"):
                         with st.spinner(f"Generating for {ch['title']}..."):
                            provider_code = "google" if provider == "Google Gemini" else "openrouter"
                            csv_text = process_chunk(
                                ch['text'], 
                                provider=provider_code,
                                model_name=model_name,
                                card_length=card_length,
                                card_density=card_density,
                                enable_highlighting=enable_highlighting,
                                custom_prompt=custom_prompt
                            )
                            try:
                                df_single = pd.read_csv(StringIO(csv_text), sep="|", names=["Front", "Back"], engine="python", quotechar='"', on_bad_lines='skip')
                                st.success(f"Generated {len(df_single)} cards!")
                                st.dataframe(df_single)
                                # Allow download
                                single_csv = df_single.to_csv(sep="|", index=False, header=False, quoting=1)
                                st.download_button(f"Download {ch['title']}.csv", single_csv, f"{ch['title']}.csv", "text/csv", key=f"dl_{idx}")
                            except Exception as e:
                                st.error(f"Parsing Error: {e}")
                                if developer_mode: st.code(csv_text)
                    
                    if new_title != ch['title']:
                        st.session_state['chapters_data'][idx]['title'] = new_title

# ==================== GENERAL AI CHAT COLUMN ====================
with col_chat:
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
                provider_code = "google" if provider == "Google Gemini" else "openrouter"
                with st.spinner("Thinking..."):
                    response = get_chat_response(
                        st.session_state.general_messages, 
                        "",  # No context for general chat
                        provider_code, 
                        model_name,
                        direct_chat=True
                    )
                st.markdown(response)
        
        st.session_state.general_messages.append({"role": "assistant", "content": response})
        st.rerun()

if not api_key:
    st.toast("⚠️ API Key not configured")

