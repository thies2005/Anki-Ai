import streamlit as st
import pandas as pd
from io import StringIO
import os
from dotenv import load_dotenv

load_dotenv()
from utils.pdf_processor import extract_text_from_pdf, clean_text, recursive_character_text_splitter, get_pdf_front_matter, extract_chapters_from_pdf
from utils.llm_handler import configure_gemini, configure_openrouter, process_chunk, get_chat_response, sort_files_with_gemini, generate_chapter_summary, generate_full_summary, detect_chapters_in_text, split_text_by_chapters, analyze_toc_with_gemini, extract_json_from_text
from utils.data_processing import robust_csv_parse, push_card_to_anki, deduplicate_cards
from utils.rag import SimpleVectorStore
import json

# Versioning
VERSION = "v2.5.0"

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

# Sidebar: Config
with st.sidebar:
    st.header("Configuration")
    
    # Provider Selection
    provider = st.radio("AI Provider", ["Google Gemini", "OpenRouter"], index=0)
    
    # Initialize session state for clients if not present
    if "google_client" not in st.session_state:
        st.session_state.google_client = None
    if "openrouter_client" not in st.session_state:
        st.session_state.openrouter_client = None

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
        summary_model = "gemma-3-27b-it" # For Google: use Gemma
    
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
    show_general_chat = st.toggle("Show General AI Chat", value=False, help="Enable the general AI chat panel on the right side")
    
    st.divider()
    if st.button("🔒 Clear Session & Keys", type="secondary"):
        st.session_state.clear()
        st.rerun()

# Split View
st.divider()
if show_general_chat:
    col_gen, col_chat = st.columns([5, 4])
else:
    col_gen = st.container()
    col_chat = None

# ==================== ANKI GENERATOR COLUMN ====================
with col_gen:
    st.subheader("1. Card Generator")
    
    with st.expander("Formatting Options", expanded=False):
        card_length = st.select_slider("Answer Length", options=["Short (1-2 words)", "Medium (Standard)", "Long (Conceptual)"], value="Medium (Standard)")
        card_density = st.select_slider("Card Count / Density", options=["Low (Key Concepts)", "Normal", "High (Comprehensive)"], value="Normal")
        enable_highlighting = st.toggle("Highlight Key Terms (Bold)", value=True)
        custom_prompt = st.text_area("Custom Instructions", help="E.g., 'Focus on Pharmacology'")
        deck_type = st.radio("Deck Organization", ["Subdecks (Base::Item)", "Tags Only (Deck: Base, Tag: Item)", "Both"], help="Organization structure.")
        formatting_mode = st.radio("Card Formatting", ["Basic + MathJax", "Markdown", "Legacy LaTeX"], index=0, help="Basic + MathJax = works with default Anki. Markdown = styled text. Legacy LaTeX = [latex]...[/latex] tags.")
        detect_chapters = st.toggle("Auto-Detect Chapters within PDFs", value=False, help="Uses AI to split each PDF into individual chapters for better deck organization.")
        
        # New Deck Name Field
        uploaded_files_preview = st.session_state.get("anki_uploader", [])
        default_deck = "Anki-AI"
        if uploaded_files_preview:
            first_fname = uploaded_files_preview[0].name.replace(".pdf", "").replace("_", " ").title()
            default_deck = f"Anki-AI: {first_fname}"
        
        base_deck_name = st.text_input("Base Deck Name", value=default_deck, help="The top-level deck name in Anki.")

    uploaded_files = st.file_uploader("Upload Medical PDF(s)", type=["pdf"], accept_multiple_files=True, key="anki_uploader")

    if uploaded_files and api_key:
        # Processing Logic
        if st.button("Process Files & Generate Summaries", type="secondary"):
             with st.spinner("Processing files..."):
                file_map = {f.name: f for f in uploaded_files}
                sorted_names = list(file_map.keys())
                
                file_chapters = []
                progress_text = st.empty()
                
                # Init Vector Store
                if 'vector_store' not in st.session_state:
                    st.session_state.vector_store = SimpleVectorStore()
                
                # Clear previous data
                st.session_state['chapters_data'] = []
                st.session_state.vector_store.clear()
                
                for idx, name in enumerate(sorted_names):
                    if name in file_map:
                        f = file_map[name]
                        fname = f.name.replace(".pdf", "").replace("_", " ").title()
                        
                        # Chapter Detection Option
                        if detect_chapters:
                            progress_text.text(f"Extracting text from {name}...")
                            text = extract_text_from_pdf(f)
                            
                            progress_text.text(f"Detecting chapters in {name} using AI...")
                            # Use text-based chapter detection with the normal model (same as Anki cards)
                            detected_chapters = detect_chapters_in_text(text, fname, google_client=st.session_state.google_client, openrouter_client=st.session_state.openrouter_client, model_name=model_name)
                            
                            if detected_chapters:
                                progress_text.text(f"Splitting {name} into {len(detected_chapters)} chapters...")
                                chapter_texts = split_text_by_chapters(text, detected_chapters)
                                
                                if chapter_texts:
                                    # Successfully split into chapters
                                    for ch_data in chapter_texts:
                                        ch_title = ch_data['title']
                                        ch_text = ch_data['text']
                                        
                                        # Use robust cleaner
                                        ch_text_cleaned = clean_text(ch_text)
                                        
                                        # Generate summary
                                        try:
                                            ch_summary = generate_chapter_summary(ch_text_cleaned, google_client=st.session_state.google_client, openrouter_client=st.session_state.openrouter_client, model_name=summary_model)
                                        except:
                                            ch_summary = "(Summary generation failed)"
                                        
                                        # Index for RAG
                                        chunks = recursive_character_text_splitter(ch_text_cleaned, chunk_size=2000)
                                        st.session_state.vector_store.add_chunks(chunks, google_client=st.session_state.google_client, metadata_list=[{"source": f"{fname} - {ch_title}"}]*len(chunks))
                                        
                                        file_chapters.append({
                                            "title": f"{fname} - {ch_title}",
                                            "text": ch_text_cleaned,
                                            "summary": ch_summary,
                                            "parent_file": fname
                                        })
                                    continue  # Move to next file

                        
                        # Default: treat entire file as one chapter
                        progress_text.text(f"Processing full text of {name}...")
                        text = extract_text_from_pdf(f)
                        cleaned_text = clean_text(text)
                        
                        # Index for RAG
                        chunks = recursive_character_text_splitter(cleaned_text, chunk_size=2000)
                        st.session_state.vector_store.add_chunks(chunks, google_client=st.session_state.google_client, metadata_list=[{"source": fname}]*len(chunks))

                        try:
                            summary = generate_chapter_summary(cleaned_text, google_client=st.session_state.google_client, openrouter_client=st.session_state.openrouter_client, model_name=summary_model)
                        except:
                            summary = "(Summary generation failed)"
                        
                        file_chapters.append({
                            "title": fname,
                            "text": cleaned_text,
                            "summary": summary,
                            "parent_file": fname
                        })
                
                st.session_state['chapters_data'] = file_chapters
                st.toast(f"Processed {len(file_chapters)} {'chapters' if detect_chapters else 'files'}", icon="📚")
        
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
                            with st.spinner("Thinking (RAG)..."):
                                # RAG Retrieval
                                    context_text = ""
                                if 'vector_store' in st.session_state:
                                    relevant_chunks = st.session_state.vector_store.search(pdf_prompt, google_client=st.session_state.google_client, k=5)
                                    context_text = "\n\n".join([c['text'] for c in relevant_chunks])
                                else:
                                    # Fallback to full context if store missing
                                    context_text = all_text_context[:100000]

                                response = get_chat_response(
                                    st.session_state.pdf_messages, 
                                    context_text, 
                                    provider_code, 
                                    model_name,
                                    google_client=st.session_state.google_client,
                                    openrouter_client=st.session_state.openrouter_client,
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
                    
                    if 'generated_questions' not in st.session_state:
                        st.session_state['generated_questions'] = []
                    
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
                                google_client=st.session_state.google_client,
                                openrouter_client=st.session_state.openrouter_client,
                                provider=provider_code,
                                model_name=model_name,
                                card_length=card_length,
                                card_density=card_density,
                                enable_highlighting=enable_highlighting,
                                custom_prompt=custom_prompt,
                                formatting_mode=formatting_mode,
                                existing_topics=st.session_state['generated_questions']
                            )
                            
                            if csv_chunk and not csv_chunk.startswith("Error"):
                                try:
                                    df_chunk = robust_csv_parse(csv_chunk)
                                    if not df_chunk.empty:
                                         # Deduplicate against existing questions
                                         df_chunk = deduplicate_cards(df_chunk, st.session_state['generated_questions'])
                                         
                                    if not df_chunk.empty:
                                         # Track generated questions for future anti-duplication
                                         new_questions = df_chunk["Front"].tolist()
                                         st.session_state['generated_questions'].extend(new_questions)
                                    
                                    clean_title = chapter['title'].replace(" ", "_").replace(":", "-")
                                    parent_file = chapter.get('parent_file', chapter['title']).replace(" ", "_").replace(":", "-")
                                    
                                    if "Subdecks" in deck_type:
                                        # If chapters detected, create: Base::ParentFile::Chapter
                                        if 'parent_file' in chapter and chapter['parent_file'] != chapter['title']:
                                            df_chunk["Deck"] = f"{base_deck_name}::{parent_file}::{clean_title}"
                                        else:
                                            df_chunk["Deck"] = f"{base_deck_name}::{clean_title}"
                                        df_chunk["Tag"] = ""
                                    elif "Tags" in deck_type:
                                         df_chunk["Deck"] = base_deck_name
                                         df_chunk["Tag"] = clean_title
                                    else:
                                         if 'parent_file' in chapter and chapter['parent_file'] != chapter['title']:
                                             df_chunk["Deck"] = f"{base_deck_name}::{parent_file}::{clean_title}"
                                         else:
                                             df_chunk["Deck"] = f"{base_deck_name}::{clean_title}"
                                         df_chunk["Tag"] = clean_title
                                    all_dfs.append(df_chunk)
                                except Exception as e:
                                    if developer_mode:
                                        st.warning(f"Failed to parse chunk: {e}")
                                        st.code(csv_chunk)
                    
                    progress_bar.progress(1.0)
                    if all_dfs:
                        final_df = pd.concat(all_dfs, ignore_index=True)
                        final_df = final_df[["Front", "Back", "Deck", "Tag"]]
                        st.session_state['result_df'] = final_df
                        # Create proper Anki TSV with header comments
                        anki_header = "#separator:tab\n#deck column:3\n#tags column:4\n"
                        tsv_content = final_df.to_csv(sep="\t", index=False, header=False, quoting=1)
                        st.session_state['result_csv'] = anki_header + tsv_content
                        st.success(f"Generated {len(final_df)} cards!")
                    else:
                        st.error("No cards generated. Check errors above.")
                except Exception as e:
                    st.error(f"Error: {e}")

            if 'result_df' in st.session_state:
                st.dataframe(st.session_state['result_df'], width='stretch')
                
                col_dl, col_push = st.columns(2)
                with col_dl:
                     st.download_button("Download anki_cards.txt", st.session_state['result_csv'], "anki_cards.txt", "text/plain")
                
                with col_push:
                     if st.button("🚀 Push to Anki (AnkiConnect)"):
                         success_count = 0
                         total = len(st.session_state['result_df'])
                         my_bar = st.progress(0)
                         
                         for i, row in st.session_state['result_df'].iterrows():
                             tags = [row['Tag']] if row['Tag'] else []
                             if push_card_to_anki(row['Front'], row['Back'], row['Deck'], tags):
                                 success_count += 1
                             my_bar.progress(min((i+1)/total, 1.0))
                         
                         if success_count > 0:
                             st.success(f"Pushed {success_count}/{total} cards!")
                         else:
                             st.warning("Failed to push. Ensure Anki is open and AnkiConnect is installed.")
            
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
                                google_client=st.session_state.google_client,
                                openrouter_client=st.session_state.openrouter_client,
                                provider=provider_code,
                                model_name=model_name,
                                card_length=card_length,
                                card_density=card_density,
                                enable_highlighting=enable_highlighting,
                                custom_prompt=custom_prompt,
                                formatting_mode=formatting_mode,
                                existing_topics=[] 
                            )
                            try:
                                df_single = robust_csv_parse(csv_text)
                                clean_title = ch['title'].replace(" ", "_").replace(":", "-")
                                df_single["Deck"] = f"{base_deck_name}::{clean_title}"
                                df_single["Tag"] = clean_title
                                anki_header = "#separator:tab\n#deck column:3\n#tags column:4\n"
                                single_tsv = anki_header + df_single.to_csv(sep="\t", index=False, header=False, quoting=1)
                                
                                # Store in session state to persist
                                st.session_state[f"result_df_{idx}"] = df_single
                                st.session_state[f"result_csv_{idx}"] = single_tsv
                                
                            except Exception as e:
                                st.error(f"Parsing Error: {e}")
                                if developer_mode: st.code(csv_text)
                    
                    # Persistent Results UI
                    res_df_key = f"result_df_{idx}"
                    res_csv_key = f"result_csv_{idx}"
                    
                    if res_df_key in st.session_state:
                        df_s = st.session_state[res_df_key]
                        csv_s = st.session_state[res_csv_key]
                        
                        st.dataframe(df_s)
                        
                        col_single_dl, col_single_push = st.columns(2)
                        with col_single_dl:
                            st.download_button(f"Download {ch['title']}.txt", csv_s, f"{ch['title']}.txt", "text/plain", key=f"dl_btn_{idx}")
                        
                        with col_single_push:
                            if st.button(f"🚀 Push {ch['title']} to Anki", key=f"push_btn_{idx}"):
                                success_count = 0
                                total = len(df_s)
                                my_bar = st.progress(0)
                                
                                for i, row in df_s.iterrows():
                                    tags = [row['Tag']] if row['Tag'] else []
                                    if push_card_to_anki(row['Front'], row['Back'], row['Deck'], tags):
                                        success_count += 1
                                    my_bar.progress(min((i+1)/total, 1.0))
                                
                                if success_count > 0:
                                    st.success(f"Pushed {success_count}/{total} cards!")
                                else:
                                    st.warning("Failed to push. Ensure Anki is open and AnkiConnect is installed.")
                    
                    if new_title != ch['title']:
                        st.session_state['chapters_data'][idx]['title'] = new_title

# ==================== GENERAL AI CHAT COLUMN ====================
if show_general_chat and col_chat is not None:
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
                            google_client=st.session_state.google_client,
                            openrouter_client=st.session_state.openrouter_client,
                            direct_chat=True
                        )
                    st.markdown(response)
            
            st.session_state.general_messages.append({"role": "assistant", "content": response})
            st.rerun()

if not api_key:
    st.toast("⚠️ API Key not configured")

