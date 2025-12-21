import streamlit as st
import pandas as pd
from io import StringIO
import os
from dotenv import load_dotenv

load_dotenv()
from utils.pdf_processor import extract_text_from_pdf, clean_text, recursive_character_text_splitter
from utils.llm_handler import configure_gemini, process_chunk_with_gemini

# Page Config
st.set_page_config(
    page_title="Medical PDF to Anki",
    page_icon="🩺",
    layout="wide"
)

# Title and Intro
st.title("🩺 Medical PDF to Anki Converter (AI-Powered)")
st.markdown("""
Convert large medical PDFs into high-yield Anki cards using **Top Tier Gemini Models**. 
Features: **USMLE focus**, **LaTeX math support**, **Smart chapter splitting**, and **AI Summaries**.
""")

# Sidebar: Config
with st.sidebar:
    st.header("Configuration")
    # API Key Input
    # API Key Input
    st.markdown("Get your API key from [Google AI Studio](https://aistudio.google.com/app/api-keys)")
    user_api_key = st.text_input("Gemini API Key", type="password", help="Leave empty to use the built-in fallback keys.")
    
    # Load Fallback Keys from .env
    from dotenv import load_dotenv
    import os
    load_dotenv()
    
    fallback_keys = []
    for i in range(1, 11):
        key = os.getenv(f"FALLBACK_KEY_{i}")
        if key and key.strip():
            fallback_keys.append(key.strip())
            
    # Init api_key
    api_key = None

    if user_api_key:
        api_key = user_api_key
        # Use fallback keys as backup
        configure_gemini(api_key, fallback_keys=fallback_keys)
        st.success(f"Custom API Key configured! (With {len(fallback_keys)} Backups)")
    else:
        if fallback_keys:
            api_key = fallback_keys[0]
            # Use remaining keys as fallback
            configure_gemini(api_key, fallback_keys=fallback_keys[1:])
            st.info(f"Using Fallback API Key 1 (Dev Mode)")
        else:
            st.error("No API Keys found (Custom or Fallback).")
            api_key = None
            # FIX: Don't call configure_gemini with an empty string
            configure_gemini(None, fallback_keys=[])
    
    st.divider()
    
    # Model Selection with descriptions
    model_options = {
        "gemini-2.5-flash-lite": "Flash 2.5 Lite - Fastest, best for simple extraction",
        "gemini-3-flash-preview": "Flash 3.0 Preview - Balanced speed & reasoning",
        "gemini-2.5-pro": "Pro 2.5 - High reasoning, best for complex content",
        "gemini-3-pro-preview": "Pro 3.0 Preview - Experimental high intelligence"
    }
    
    selected_model_key = st.selectbox(
        "Model", 
        options=list(model_options.keys()), 
        format_func=lambda x: model_options[x],
        index=0
    )
    model_name = selected_model_key
    chunk_size = st.slider("Chunk Size (chars)", 5000, 20000, 10000, step=1000)
    
    st.divider()
    st.subheader("Card Style Configuration")
    card_length = st.select_slider("Answer Length", options=["Short (1-2 words)", "Medium (Standard)", "Long (Conceptual)"], value="Medium (Standard)")
    card_density = st.select_slider("Card Count / Density", options=["Low (Key Concepts)", "Normal", "High (Comprehensive)"], value="Normal")
    enable_highlighting = st.toggle("Highlight Key Terms (Bold)", value=True, help="Bold specific high-yield terms in the answer.")
    custom_prompt = st.text_area("Custom Instructions (Optional)", help="Add specific rules or focus areas (e.g., 'Focus ONLY on Pharmacology').")
    
    st.divider()
    deck_type = st.radio("Deck Organization", ["Subdecks (Medical::Item)", "Tags Only (Deck: Medical, Tag: Item)", "Both (Subdecks + Tags)"], help="Subdecks: Creates new decks. Tags: Uses one deck with tags. Both: Uses subdecks AND tags.")
    developer_mode = st.toggle("Developer Mode (Debug Logs)", value=False, help="Show raw LLM outputs and detailed error logs.")

# Main Area: Upload
uploaded_files = st.file_uploader("Upload Medical PDF(s)", type=["pdf"], accept_multiple_files=True)

if uploaded_files and api_key:
    st.divider()
    col1, col2 = st.columns([1, 2])
    
    # Logic Split
    is_multi_file = len(uploaded_files) > 1
    
    with col1:
        if is_multi_file:
            st.info(f"{len(uploaded_files)} Files Uploaded")
            
            # Auto-prepare "chapters" from files
            # Check if we already processed them to avoid re-reading every rerun
            # But st.file_uploader re-runs on change.
            if st.button("1. Process Files", type="secondary"):
                 with st.spinner("Processing files..."):
                    from utils.pdf_processor import extract_text_from_pdf
                    from utils.llm_handler import sort_files_with_gemini, generate_chapter_summary, generate_full_summary
                    
                    # Sort files via AI
                    file_map = {f.name: f for f in uploaded_files}
                    sorted_names = sort_files_with_gemini(list(file_map.keys()))
                    st.toast("Files sorted by AI 🧠")
                    
                    file_chapters = []
                    collected_summaries = []
                    
                    progress_text = st.empty()
                    
                    for idx, name in enumerate(sorted_names):
                        if name in file_map:
                            progress_text.text(f"Processing & Summarizing {name}...")
                            f = file_map[name]
                            text = extract_text_from_pdf(f)
                            
                            # Summarize
                            summary = generate_chapter_summary(text)
                            collected_summaries.append(summary)
                            
                            # Clean filename
                            fname = f.name.replace(".pdf", "").replace("_", " ").title()
                            file_chapters.append({
                                "title": fname,
                                "text": text,
                                "summary": summary
                            })
                    
                    st.session_state['chapters_data'] = file_chapters
                    st.toast(f"Processed {len(file_chapters)} files", icon="📚")
                    
                    # Full Summary
                    with st.spinner("Generating document summary..."):
                        full_summary = generate_full_summary(collected_summaries)
                        st.session_state['full_summary'] = full_summary
        
        else:
            # Single File Mode - Chapter Extraction
            single_file = uploaded_files[0]
            st.info(f"File: {single_file.name}")
            
            # Step 1: Extract
            use_ai_toc = st.checkbox("Use AI Chapter Detection (Gemini 2.5 Flash Lite)", help="Use LLM to find chapters from the first 50 pages. Useful if the PDF has no clickable Table of Contents.", value=False)
            
            if st.button("1. Extract Chapters", type="secondary"):
                 with st.spinner("Extracting chapters..."):
                    from utils.pdf_processor import extract_chapters_from_pdf, get_pdf_front_matter
                    import json
                    
                    ai_toc = None
                    if use_ai_toc:
                        st.toast("Analyzing PDF structure with AI...", icon="🤖")
                        front_matter = get_pdf_front_matter(single_file)
                        from utils.llm_handler import analyze_toc_with_gemini
                        toc_json = analyze_toc_with_gemini(front_matter)
                        # Simple cleanup
                        try:
                            start = toc_json.find('[')
                            end = toc_json.rfind(']') + 1
                            if start != -1 and end != -1:
                                ai_toc = json.loads(toc_json[start:end])
                                st.info(f"AI Detected {len(ai_toc)} chapters.")
                            else:
                                st.warning("AI TOC Detection failed to return JSON.")
                        except Exception as e:
                            st.warning(f"Failed to parse AI TOC: {e}")

                    from utils.llm_handler import generate_chapter_summary, generate_full_summary
                    
                    chapters = extract_chapters_from_pdf(single_file, ai_extracted_toc=ai_toc)
                    
                    # Generate Summaries
                    collected_summaries = []
                    progress_text = st.empty()
                    for ch in chapters:
                        progress_text.text(f"Summarizing {ch['title']}...")
                        summary = generate_chapter_summary(ch['text'])
                        ch['summary'] = summary
                        collected_summaries.append(summary)
                    
                    st.session_state['chapters_data'] = chapters
                    st.toast(f"Found {len(chapters)} chapters", icon="📚")
                    
                    # Full Summary
                    with st.spinner("Generating document summary..."):
                        full_summary = generate_full_summary(collected_summaries)
                        st.session_state['full_summary'] = full_summary

    # Step 2: Edit (if extracted)
    if 'chapters_data' in st.session_state and st.session_state['chapters_data']:
        st.subheader("Edit Chapters")
        
        if 'full_summary' in st.session_state:
            with st.expander("📄 Document Summary (Gemma 2 27B)", expanded=True):
                st.markdown(st.session_state['full_summary'])
        
        # Create a form or just interactive widgets. 
        # Using specific keys to update session state directly is complex in loop.
        # Better to iterate and show widgets that write to a temp list or update session state on change.
        # We will use on_change callbacks or just read values at the end? 
        # Simple approach: Render widgets with values from session state.
        
        for idx, ch in enumerate(st.session_state['chapters_data']):
            with st.expander(f"Chapter {idx+1}: {ch['title']}", expanded=False):
                # We need unique keys. 
                new_title = st.text_input(f"Title", value=ch['title'], key=f"title_{idx}")
                
                if 'summary' in ch:
                    st.caption(f"**Summary:** {ch['summary']}")
                
                new_text = st.text_area(f"Content (Preview)", value=ch['text'][:1000] + "...", height=150, key=f"text_preview_{idx}", disabled=True, help="Full text is stored but truncated here for performance.")
                
                # Single Chapter Generation
                if st.button(f"⚡ Generate Cards for '{ch['title']}' Only", key=f"gen_{idx}"):
                    with st.spinner(f"Generating cards for {ch['title']}..."):
                        # Process single chunk
                        csv_text = process_chunk_with_gemini(
                            ch['text'], 
                            model_name=model_name,
                            card_length=card_length,
                            card_density=card_density,
                            enable_highlighting=enable_highlighting,
                            custom_prompt=custom_prompt
                        )
                        
                        # Convert to DataFrame to add Tags/Decks
                        from io import StringIO
                        try:
                            # Parse assuming | delimiter
                            df_single = pd.read_csv(StringIO(csv_text), sep="|", names=["Front", "Back"], engine="python", quotechar='"')
                            
                            # Add Metadata
                            clean_subdeck = ch['title'].replace(":", "-").replace("|", "-").strip()
                            if "Subdecks" in deck_type:
                                df_single['Deck'] = f"Medical::{clean_subdeck}"
                                df_single['Tag'] = "" 
                            elif "Tags" in deck_type:
                                df_single['Deck'] = "Medical"
                                df_single['Tag'] = clean_subdeck
                            else: # Both
                                df_single['Deck'] = f"Medical::{clean_subdeck}"
                                df_single['Tag'] = clean_subdeck

                            # Convert back to CSV with Anki Headers
                            # Ensure columns are ordered: Front, Back, Deck, Tag
                            df_single = df_single[["Front", "Back", "Deck", "Tag"]]
                            
                            csv_body = df_single.to_csv(index=False, sep="|", header=False)
                            final_csv_single = f"#separator:Pipe\n#html:true\n#columns:Front|Back|Deck|Tag\n{csv_body}"
                            
                            st.success(f"Generated {len(df_single)} cards for {ch['title']}!")
                            st.download_button(
                                label=f"Download {ch['title']}.csv",
                                data=final_csv_single,
                                file_name=f"Anki_{clean_subdeck}.csv",
                                mime="text/csv",
                                key=f"dl_{idx}"
                            )
                        except Exception as e:
                            st.error(f"Failed to parse generated CSV: {e}")
                            if developer_mode:
                                st.code(csv_text)
                # If user wants to edit text, we need a better editor. 
                # For now, let's allow Title editing which is critical for Subdecks.
                
                if new_title != ch['title']:
                    st.session_state['chapters_data'][idx]['title'] = new_title

    # Step 3: Generate
    if 'chapters_data' in st.session_state and st.session_state['chapters_data']:
        st.divider()
        if st.button("2. Generate Anki Cards", type="primary"):
            try:
                
                # 2. Process Each Chapter/File from Session State
                if 'chapters_data' not in st.session_state:
                     st.error("No data found. Please extract chapters or process files first.")
                     st.stop()
                
                total_chapters = len(st.session_state['chapters_data'])
                all_dfs = []
                
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                for ch_idx, chapter in enumerate(st.session_state['chapters_data']):
                    chapter_title = chapter['title']
                    raw_text = chapter['text']
                    
                    # Clean and split
                    cleaned_text = clean_text(raw_text)
                    chunks = recursive_character_text_splitter(cleaned_text, chunk_size=chunk_size)
                    
                    status_text.text(f"Processing Chapter {ch_idx+1}/{total_chapters}: {chapter_title} ({len(chunks)} chunks)")
                    
                    for chunk_idx, chunk in enumerate(chunks):
                        # Calculate global progress (approximate)
                        # A better way would be counting total chunks first, but that requires pre-processing. 
                        # We'll just update based on chapter fraction.
                        current_progress = (ch_idx + (chunk_idx / len(chunks))) / total_chapters
                        progress_bar.progress(min(current_progress, 1.0))
                        
                        # Process with Gemini
                        csv_chunk = process_chunk_with_gemini(
                            chunk, 
                            model_name=model_name,
                            card_length=card_length,
                            card_density=card_density,
                            enable_highlighting=enable_highlighting,
                            custom_prompt=custom_prompt
                        )
                        
                        if developer_mode:
                            with st.expander(f"Debug: Chunk {chunk_idx+1} Raw Output"):
                                st.text(csv_chunk)
                        
                        if csv_chunk and not csv_chunk.startswith("Error"):
                            try:
                                # Parse chunk to DF
                                # Use python engine with strict quote handling
                                df_chunk = pd.read_csv(
                                    StringIO(csv_chunk), 
                                    sep="|", 
                                    names=["Front", "Back"], 
                                    engine="python",
                                    quotechar='"',
                                    on_bad_lines='skip' # robust parsing
                                )
                                
                                clean_title = chapter_title.replace(" ", "_").replace(":", "-")
                                if "Subdecks" in deck_type and "Tags" not in deck_type:
                                    df_chunk["Tag"] = "Medical_AI" # Default general tag
                                    df_chunk["Deck"] = f"Medical::{chapter_title}"
                                elif "Tags" in deck_type and "Subdecks" not in deck_type:
                                    df_chunk["Tag"] = clean_title
                                    df_chunk["Deck"] = "Medical"
                                else: # Both
                                    df_chunk["Tag"] = clean_title
                                    df_chunk["Deck"] = f"Medical::{chapter_title}"
                                
                                all_dfs.append(df_chunk)
                            except Exception as parse_err:
                                st.warning(f"Failed to parse a chunk in '{chapter_title}': {parse_err}")
                                # continue
                
                progress_bar.progress(1.0)
                status_text.text("Aggregation complete!")

                # 3. Final Aggregation
                if all_dfs:
                    final_df = pd.concat(all_dfs, ignore_index=True)
                    
                    # Convert to CSV
                    # Anki standard: no header usually, or header ignored. 
                    # We will provide a headerless CSV or with header? 
                    # User asked for "csv with chapters and tags". 
                    # Let's include header if they want to inspect, but for Anki import, usually we turn 'allow HTML in fields' on.
                    # We will output WITH header for clarity in the preview, but maybe offer a toggle?
                    # For now: No header to conform to previous behavior, but 4 columns.
                    # Output columns: Front, Back, Deck, Tag
                    # Reorder to ensure consistency
                    final_df = final_df[["Front", "Back", "Deck", "Tag"]]
                    
                    csv_body = final_df.to_csv(sep="|", index=False, header=False, quoting=1) # quoting=1 means csv.QUOTE_ALL
                    final_csv_string = f"#separator:Pipe\n#html:true\n#columns:Front|Back|Deck|Tag\n{csv_body}"
                    
                    st.session_state['result_df'] = final_df
                    st.session_state['result_csv'] = final_csv_string
                    st.success(f"Processing Complete! Generated {len(final_df)} cards.")
                else:
                    st.error("No valid cards generated.")

            except Exception as e:
                st.error(f"An error occurred: {e}")

if 'result_df' in st.session_state:
    st.subheader("Preview Generated Cards")
    st.dataframe(st.session_state['result_df'], use_container_width=True)

if 'result_csv' in st.session_state:
    st.download_button(
        label="Download anki_medical_cards.csv",
        data=st.session_state['result_csv'],
        file_name="anki_medical_cards.csv",
        mime="text/csv"
    )

if not api_key:
    st.warning("Please enter your Gemini API Key in the sidebar to proceed.")
