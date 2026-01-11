"""
Card generator component.
"""
import streamlit as st
import pandas as pd
import logging
from utils.pdf_processor import extract_text_from_pdf, clean_text, recursive_character_text_splitter
from utils.llm_handler import process_chunk, generate_chapter_summary, detect_chapters_in_text, split_text_by_chapters
from utils.data_processing import robust_csv_parse, push_card_to_anki, deduplicate_cards, check_ankiconnect, format_cards_for_ankiconnect
import streamlit.components.v1 as components
import json
from utils.rag import SQLiteVectorStore

logger = logging.getLogger(__name__)

# Constants
MAX_FILE_SIZE_MB = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

def render_generator(config):
    """Renders the card generator interface."""
    provider = config["provider"]
    api_key = config["api_key"]
    model_name = config["model_name"]
    summary_model = config["summary_model"]
    chunk_size = config["chunk_size"]
    developer_mode = config["developer_mode"]

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
    
    # Validate file sizes
    valid_files = []
    if uploaded_files:
        for f in uploaded_files:
            if f.size > MAX_FILE_SIZE_BYTES:
                st.warning(f"⚠️ {f.name} exceeds {MAX_FILE_SIZE_MB}MB limit and will be skipped.")
            else:
                valid_files.append(f)
        uploaded_files = valid_files

    if uploaded_files and api_key:
        # Processing Logic
        if st.button("Process Files & Generate Summaries", type="secondary"):
             with st.spinner("Processing files..."):
                file_map = {f.name: f for f in uploaded_files}
                sorted_names = list(file_map.keys())
                
                file_chapters = []
                progress_text = st.empty()
                
                # Init Vector Store
                if not st.session_state.get('vector_store'):
                    st.session_state.vector_store = SQLiteVectorStore()
                
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
                                        
                                        try:
                                            ch_summary = generate_chapter_summary(ch_text_cleaned, google_client=st.session_state.google_client, openrouter_client=st.session_state.openrouter_client, model_name=summary_model)
                                        except Exception as e:
                                            logger.warning(f"Summary generation failed for {ch_title}: {e}")
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
                        except Exception as e:
                            logger.warning(f"Summary failed for {name}: {e}")
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
                st.dataframe(st.session_state['result_df'], use_container_width=True)
                
                col_dl, col_push, col_browser = st.columns(3)
                with col_dl:
                     st.download_button("Download anki_cards.txt", st.session_state['result_csv'], "anki_cards.txt", "text/plain")
                
                with col_push:
                     if st.button("🚀 Push (via Server)", help="Uses tunnel if on Cloud, or direct if local."):
                         # Get URL from session state
                         anki_url = st.session_state.get('anki_connect_url', 'http://localhost:8765')
                         
                         # Check connection first
                         is_reachable, msg = check_ankiconnect(anki_url)
                         if not is_reachable:
                             st.error(f"❌ {msg}")
                         else:
                             st.info(f"✅ {msg}")
                             success_count = 0
                             total = len(st.session_state['result_df'])
                             my_bar = st.progress(0)
                             
                             for i, row in st.session_state['result_df'].iterrows():
                                 tags = [row['Tag']] if row['Tag'] else []
                                 if push_card_to_anki(row['Front'], row['Back'], row['Deck'], tags, anki_url):
                                     success_count += 1
                                 my_bar.progress(min((i+1)/total, 1.0))
                             
                             if success_count > 0:
                                 st.success(f"Pushed {success_count}/{total} cards!")
                             else:
                                 st.warning("Cards were not added. They may already exist in the deck.")
                
                with col_browser:
                    if st.button("🌐 Direct Browser Push", help="Works from Cloud without a tunnel. Requires AnkiConnect CORS set to '*'"):
                        notes = format_cards_for_ankiconnect(st.session_state['result_df'])
                        notes_json = json.dumps(notes)
                        
                        js_code = f"""
                        <script>
                        async function pushToAnki() {{
                            const notes = {notes_json};
                            const payload = {{
                                "action": "addNotes",
                                "version": 6,
                                "params": {{ "notes": notes }}
                            }};
                            try {{
                                const response = await fetch('http://localhost:8765', {{
                                    method: 'POST',
                                    body: JSON.stringify(payload),
                                    headers: {{ 'Content-Type': 'application/json' }}
                                }});
                                const result = await response.json();
                                if (result.error) {{
                                    alert('AnkiConnect Error: ' + result.error);
                                }} else {{
                                    const successCount = result.result.filter(id => id !== null).length;
                                    alert('Successfully pushed ' + successCount + ' cards via Browser!');
                                }}
                            }} catch (err) {{
                                alert('Failed to connect to Local Anki. Ensure Anki is open and CORS is set to "*" in AnkiConnect config.');
                            }}
                        }}
                        pushToAnki();
                        </script>
                        """
                        components.html(js_code, height=0)
            
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
                        
                        col_single_dl, col_single_push, col_single_browser = st.columns(3)
                        with col_single_dl:
                            st.download_button(f"Download {ch['title']}.txt", csv_s, f"{ch['title']}.txt", "text/plain", key=f"dl_btn_{idx}")
                        
                        with col_single_push:
                            if st.button(f"🚀 Push (Server)", key=f"push_btn_{idx}"):
                                anki_url = st.session_state.get('anki_connect_url', 'http://localhost:8765')
                                is_reachable, msg = check_ankiconnect(anki_url)
                                if not is_reachable:
                                    st.error(f"❌ {msg}")
                                else:
                                    success_count = 0
                                    total = len(df_s)
                                    my_bar = st.progress(0)
                                    
                                    for i, row in df_s.iterrows():
                                        tags = [row['Tag']] if row['Tag'] else []
                                        if push_card_to_anki(row['Front'], row['Back'], row['Deck'], tags, anki_url):
                                            success_count += 1
                                        my_bar.progress(min((i+1)/total, 1.0))
                                    
                                    if success_count > 0:
                                        st.success(f"Pushed {success_count}/{total} cards!")
                                    else:
                                        st.warning("Cards were not added. They may already exist in the deck.")
                        
                        with col_single_browser:
                            if st.button(f"🌐 Push (Browser)", key=f"browser_push_btn_{idx}"):
                                notes = format_cards_for_ankiconnect(df_s)
                                notes_json = json.dumps(notes)
                                
                                js_code = f"""
                                <script>
                                async function pushToAnkiSingle() {{
                                    const notes = {notes_json};
                                    const payload = {{
                                        "action": "addNotes",
                                        "version": 6,
                                        "params": {{ "notes": notes }}
                                    }};
                                    try {{
                                        const response = await fetch('http://localhost:8765', {{
                                            method: 'POST',
                                            body: JSON.stringify(payload),
                                            headers: {{ 'Content-Type': 'application/json' }}
                                        }});
                                        const result = await response.json();
                                        if (result.error) {{
                                            alert('AnkiConnect Error: ' + result.error);
                                        }} else {{
                                            const successCount = result.result.filter(id => id !== null).length;
                                            alert('Successfully pushed ' + successCount + ' cards for {ch['title']} via Browser!');
                                        }}
                                    }} catch (err) {{
                                        alert('Failed to connect to Local Anki. Ensure Anki is open and CORS is set to "*" in AnkiConnect config.');
                                    }}
                                }}
                                pushToAnkiSingle();
                                </script>
                                """
                                components.html(js_code, height=0)
                    
                    if new_title != ch['title']:
                        st.session_state['chapters_data'][idx]['title'] = new_title

    if not api_key:
        st.toast("⚠️ API Key not configured")
