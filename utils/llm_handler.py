from google import genai
from google.genai import types
import os

# Global client holder (simple implementation)
# Global client holders
_PRIMARY_CLIENT = None
_FALLBACK_CLIENTS = []

def configure_gemini(api_key: str, fallback_keys: list = None):
    """Configures the Gemini API with provided primary and fallback keys."""
    global _PRIMARY_CLIENT, _FALLBACK_CLIENTS
    _PRIMARY_CLIENT = genai.Client(api_key=api_key)
    _FALLBACK_CLIENTS = []
    if fallback_keys:
        for key in fallback_keys:
            if key and key.strip():
                 try:
                    _FALLBACK_CLIENTS.append(genai.Client(api_key=key))
                 except: 
                    pass

import time

def rate_limit_delay(model_name: str):
    """Enforces rate limits: 30 RPM for Gemma, 10 RPM for Flash Lite, 5 RPM for others."""
    if "gemma" in model_name:
        delay = 2.0 # 30 RPM
    elif "flash-lite" in model_name:
        delay = 6.0 # 10 RPM
    else:
        delay = 12.0 # 5 RPM
    time.sleep(delay)

def _generate_with_retry(model_name: str, contents, config, fallback_to_flash_lite: bool = False):
    """
    Centralized generation with Key Rotation (Primary -> Fallbacks) and optional Model Fallback.
    """
    global _PRIMARY_CLIENT, _FALLBACK_CLIENTS
    
    if not _PRIMARY_CLIENT:
        # Compatibility check
        if '_CLIENT' in globals() and globals()['_CLIENT']:
             _PRIMARY_CLIENT = globals()['_CLIENT']
        else:
             raise ValueError("API Key not configured.")
        
    rate_limit_delay(model_name)
    
    # Helper to attempt generation on a specific client
    def attempt(client, model):
        return client.models.generate_content(
            model=model,
            contents=contents,
            config=config
        )
        
    errors = []
    
    # 1. Try Primary Key
    try:
        return attempt(_PRIMARY_CLIENT, model_name)
    except Exception as e:
        errors.append(f"Primary Key Error: {str(e)}")
        # Check for Rate Limit / Quota / Auth errors to trigger switch
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e) or "403" in str(e):
             # 2. Try Fallback Keys
             for idx, client in enumerate(_FALLBACK_CLIENTS):
                 try:
                     time.sleep(1) # Brief pause before switching
                     return attempt(client, model_name)
                 except Exception as e2:
                     errors.append(f"Fallback Key {idx+1} Error: {str(e2)}")
                     continue # Try next key
    
    # 3. Model Fallback (Flash Lite)
    # Triggered if all keys failed AND fallback enabled
    if fallback_to_flash_lite:
        try:
            # Fallback uses Primary Key (assuming quota might be per-model or per-tier)
            # Ideally we could rotate keys for this too, but for simplicity starts with Primary.
            return attempt(_PRIMARY_CLIENT, "gemini-2.5-flash-lite")
        except Exception as e3:
             errors.append(f"Flash Lite Fallback Error: {str(e3)}")
             
    # If we got here, everything failed.
    raise Exception(f"All attempts failed. Errors: {'; '.join(errors)}")

def process_chunk_with_gemini(text_chunk: str, model_name: str = "gemini-3-flash", card_length: str = "Medium (Standard)", card_density: str = "Normal", enable_highlighting: bool = False, custom_prompt: str = "") -> str:
    """
    Sends a text chunk to Gemini Flash and retrieves Anki CSV cards.
    """
    # Determine Rules based on settings
    length_instruction = ""
    if "Short" in card_length:
        length_instruction = "Rule: Answers MUST be extremely concise (1-5 words maximum). Fast recall."
    elif "Long" in card_length:
        length_instruction = "Rule: Answers should be detailed and conceptual (3-5 sentences), explaining the mechanism and context."
    else:
        length_instruction = "Rule: Answers should be standard Anki length (1-2 sentences)."

    density_instruction = ""
    if "Low" in card_density:
        density_instruction = "Rule: DENSITY = LOW. Generate cards ONLY for the absolute most critical, high-yield concepts. Skip minor details."
    elif "High" in card_density:
        density_instruction = "Rule: DENSITY = HIGH. Generate comprehensive cards covering EVERY detail, mechanism, and fact in the text."
    else:
        density_instruction = "Rule: DENSITY = NORMAL. Generate a balanced set of cards covering main points and important details."

    highlight_instruction = ""
    if enable_highlighting:
        highlight_instruction = "Rule: Use bold (**text**) to highlight the most high-yield keywords/associations in the Answer."
        
    custom_instruction_str = ""
    if custom_prompt:
        custom_instruction_str = f"9. USER OVERRIDE/ADDITION: {custom_prompt}"

    config = types.GenerateContentConfig(
        system_instruction=f"""You are an expert Medical Anki Card Generator.
    
    Rules:
    1. Subject: Medical School (USMLE/High-Yield focus).
    2. Formatting: Use Markdown with KaTeX for math (e.g., $Ca^{{2+}}$ for inline, $$...$$ for block).
    3. CSV Structure: "Front"|"Back". Use a pipe | as a delimiter. WARNING: You MUST enclose EVERY field in double quotes. If a field contains a double quote, escape it by doubling it (" -> "").
    4. Content: Focus on pathophysiology, pharmacology (mechanism of action/side effects), and diagnostic gold standards. 
    5. Completeness: EVERY card MUST have a Question AND an Answer. Do not generate headers.
    6. Strictness: Output ONLY the CSV content. No code fences. One card per line.
    
    Custom Preferences:
    7. {length_instruction}
    8. {density_instruction}
    9. {highlight_instruction}
    {custom_instruction_str}
    """,
        temperature=0.2,
        max_output_tokens=65536,
    )

    try:
        response = _generate_with_retry(model_name, text_chunk, config, fallback_to_flash_lite=False)
        
        # Clean up response if it contains markdown code blocks
        text = response.text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines)
            
        return text
    except Exception as e:
        return f"Error processing chunk: {str(e)}"

def analyze_toc_with_gemini(toc_text: str, model_name: str = "gemini-2.5-flash-lite") -> str:
    """Extracts chapter structure from text using Gemini."""
    prompt = f"""You are a PDF Structure Analyzer. 
    Analyze the following text (which contains the Table of Contents of a medical textbook) and extract the hierarchical chapters.
    
    Output strictly valid JSON list of objects:
    [
        {{"title": "Chapter Title", "page": <integer_page_number>}},
        ...
    ]
    
    Rules:
    1. Ignore preface, foreword, or front matter (pages usually roman numerals or low numbers). Start with Chapter 1 if possible.
    2. Extract the main chapters or units.
    3. The 'page' must be the integer page number found in the text.
    
    Text:
    {toc_text[:30000]} 
    """

    try:
        response = _generate_with_retry(
            model_name, 
            prompt, 
            types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1),
            fallback_to_flash_lite=False
        )
        return response.text
    except Exception as e:
        return f"Error analyzing TOC: {str(e)}"

def sort_files_with_gemini(file_names: list[str], model_name: str = "gemma-3-27b-it") -> list[str]:
    """Sorts a list of filenames logically using Gemma 3 27B IT."""
    prompt = f"""Sort the following list of filenames in the most logical chronological or numerical order (e.g. Lecture 1 before Lecture 2, Chapter 1 before 10).
    
    Input List:
    {file_names}
    
    Output Strict JSON List of strings (sorted):
    ["file1.pdf", "file2.pdf", ...]
    """

    try:
        response = _generate_with_retry(
            model_name,
            prompt,
            types.GenerateContentConfig(response_mime_type="application/json", temperature=0.0),
            fallback_to_flash_lite=False 
        )
        import json
        sorted_list = json.loads(response.text)
        if len(sorted_list) == len(file_names):
            return sorted_list
        return file_names
    except:
        return file_names

def generate_chapter_summary(text_chunk: str, model_name: str = "gemma-3-27b-it") -> str:
    """Generates a brief summary of a chapter."""
    input_text = text_chunk[:30000] 
    
    try:
        response = _generate_with_retry(
            model_name,
            f"Summarize the following medical text in 3-5 concise sentences. Focus on high-yield pathologies and mechanisms.\n\nText:\n{input_text}",
            types.GenerateContentConfig(temperature=0.2),
            fallback_to_flash_lite=True
        )
        return response.text
    except Exception as e:
        return f"Summary failed: {str(e)}"

def generate_full_summary(chapter_summaries: list[str], model_name: str = "gemma-3-27b-it") -> str:
    """Aggregates chapter summaries into a document abstract."""
    joined_summaries = "\n- ".join(chapter_summaries)
    try:
        response = _generate_with_retry(
            model_name,
            f"Create a coherent summary/abstract of the entire document based on these chapter summaries:\n\n- {joined_summaries}",
            types.GenerateContentConfig(temperature=0.2),
            fallback_to_flash_lite=True
        )
        return response.text
    except Exception as e:
        return f"Full summary failed: {str(e)}"
