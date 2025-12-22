from google import genai
from google.genai import types
import os
import openai

# Global client holders
_PRIMARY_CLIENT = None
_FALLBACK_CLIENTS = []
_OPENROUTER_CLIENT = None

def configure_gemini(api_key: str, fallback_keys: list = None):
    """Configures the Gemini API with provided primary and fallback keys."""
    global _PRIMARY_CLIENT, _FALLBACK_CLIENTS
    
    # FIX: Only initialize if api_key is not empty
    if api_key and api_key.strip():
        _PRIMARY_CLIENT = genai.Client(api_key=api_key)
    else:
        _PRIMARY_CLIENT = None
        
    _FALLBACK_CLIENTS = []
    if fallback_keys:
        for key in fallback_keys:
            if key and key.strip():
                 try:
                    _FALLBACK_CLIENTS.append(genai.Client(api_key=key))
                 except: 
                    pass

def configure_openrouter(api_key: str):
    """Configures the OpenRouter API."""
    global _OPENROUTER_CLIENT
    if api_key and api_key.strip():
        _OPENROUTER_CLIENT = openai.OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
    else:
        _OPENROUTER_CLIENT = None

import time

def rate_limit_delay(model_name: str):
    """Enforces rate limits."""
    if "gemma" in model_name:
        delay = 2.0 # 30 RPM
    elif "flash-lite" in model_name:
        delay = 6.0 # 10 RPM
    elif "free" in model_name:
        delay = 3.0 # 20 RPM (Requested)
    else:
        # Default safety
        delay = 1.0 
    time.sleep(delay)

def _generate_with_retry(model_name: str, contents, config, fallback_to_flash_lite: bool = True):
    """
    Centralized generation with Key Rotation (Primary -> Fallbacks) and Model Fallback.
    """
    global _PRIMARY_CLIENT, _FALLBACK_CLIENTS
    
    if not _PRIMARY_CLIENT:
         raise ValueError("Google API Key not configured.")
        
    rate_limit_delay(model_name)
    
    # Define fallback models for Google
    google_fallbacks = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-3-flash", "gemma-3-27b-it"]
    # Ensure current model is tried first, then the others
    models_to_try = [model_name]
    if fallback_to_flash_lite:
        for m in google_fallbacks:
            if m not in models_to_try:
                models_to_try.append(m)

    # Helper to attempt generation on a specific client
    def attempt(client, model):
        return client.models.generate_content(
            model=model,
            contents=contents,
            config=config
        )
        
    errors = []
    
    for current_model in models_to_try:
        # Try Primary Key for this model
        try:
            return attempt(_PRIMARY_CLIENT, current_model)
        except Exception as e:
            err_str = str(e)
            errors.append(f"Model {current_model} (Primary Key) Error: {err_str}")
            
            # If rate limited (429) or other retryable error, try fallback keys
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "503" in err_str:
                for idx, client in enumerate(_FALLBACK_CLIENTS):
                    try:
                        time.sleep(1) # Brief pause before switching
                        return attempt(client, current_model)
                    except Exception as e2:
                        errors.append(f"Model {current_model} (Fallback Key {idx+1}) Error: {str(e2)}")
                        continue # Try next key
            
            # If it's not a 429/retryable error on primary key, don't try other keys for this model?
            # Actually, usually safer to try all keys anyway, but if it's a 400 (Bad Request), keys won't help.
            # However, for 429, we definitely want to try other keys.
            
    # If we got here, everything failed.
    raise Exception(f"All attempts failed. Errors: {'; '.join(errors)}")

def _generate_with_openrouter(model_name: str, system_instruction: str, user_content: str):
    """Generates content using OpenRouter with 429 fallback to other free models."""
    global _OPENROUTER_CLIENT
    if not _OPENROUTER_CLIENT:
        raise ValueError("OpenRouter API Key not configured.")

    # List of free models to try if the primary one fails with 429
    openrouter_fallbacks = [
        "xiaomi/mimo-v2-flash:free",
        "google/gemini-2.0-flash-exp:free",
        "mistralai/devstral-2512:free",
        "qwen/qwen3-coder:free",
        "google/gemma-3-27b-it:free"
    ]
    
    # Try the requested model first
    models_to_try = [model_name]
    for m in openrouter_fallbacks:
        if m not in models_to_try:
            models_to_try.append(m)

    errors = []
    for current_model in models_to_try:
        try:
            rate_limit_delay(current_model)
            if errors:
                time.sleep(1) # Extra pause between different model attempts
            response = _OPENROUTER_CLIENT.chat.completions.create(
                model=current_model,
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.2,
                max_tokens=16000
            )
            return response.choices[0].message.content
        except Exception as e:
            error_msg = getattr(e, 'message', str(e))
            errors.append(f"Model {current_model} Error: {error_msg}")
            
            # Only switch model on 429 (Rate Limit) or 503 (Overloaded)
            if "429" in error_msg or "rate limit" in error_msg.lower() or "503" in error_msg:
                continue
            else:
                # For other errors (like 401 Auth), stop and show error
                raise Exception(f"OpenRouter Critical Error: {error_msg}")

    raise Exception(f"All OpenRouter models failed. Errors: {'; '.join(errors[-3:])}")

def get_chat_response(messages: list, context: str, provider: str, model_name: str, direct_chat: bool = False) -> str:
    """
    Handles chat interaction.
    If direct_chat=True, it chats with the model directly without document context.
    messages: list of {"role": "user"|"assistant", "content": "..."}
    """
    if direct_chat:
        system_prompt = "You are a helpful and intelligent AI assistant. Answer the user's questions clearly and accurately."
    else:
        context_limit = 200000 if "xiaomi" in model_name.lower() else 100000
        system_prompt = f"""You are a helpful Medical Assistant AI. 
        Answer questions based strictly on the provided medical context.
        
        Context:
        {context[:context_limit]} 
        
        (Context truncated to {context_limit} chars for safety)
        """
    
    if provider == "google":
        global _PRIMARY_CLIENT
        if not _PRIMARY_CLIENT: return "Error: Google Client not configured."
        
        # Convert messages to Gemini format (user/model)
        gemini_hist = []
        for m in messages:
            role = "user" if m["role"] == "user" else "model"
            gemini_hist.append(types.Content(role=role, parts=[types.Part.from_text(text=m["content"])]))
            
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.7
        )
        
        try:
            # We use generate_content with the full history as contents, or chat session?
            # Unified generate_content is stateless-ish but we can pass list of contents.
            # But generate_content expects list of Content objects.
            response = _generate_with_retry(model_name, gemini_hist, config, fallback_to_flash_lite=True)
            return response.text
        except Exception as e:
            return f"Chat Error: {e}"

    elif provider == "openrouter":
        global _OPENROUTER_CLIENT
        if not _OPENROUTER_CLIENT: return "Error: OpenRouter Client not configured."
        
        rate_limit_delay(model_name)
        
        # OpenRouter/OpenAI Format
        # Prepend system prompt to messages
        full_messages = [{"role": "system", "content": system_prompt}] + messages
        
        try:
            response = _OPENROUTER_CLIENT.chat.completions.create(
                model=model_name,
                messages=full_messages,
                temperature=0.7
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"Chat Error: {e}"
    
    return "Error: Invalid Provider"

def process_chunk(text_chunk: str, provider: str = "google", model_name: str = "gemini-3-flash", card_length: str = "Medium (Standard)", card_density: str = "Normal", enable_highlighting: bool = False, custom_prompt: str = "", formatting_mode: str = "Markdown/HTML") -> str:
    """
    Sends a text chunk to the selected Provider/Model and retrieves Anki CSV cards.
    formatting_mode: "Plain Text", "Markdown/HTML", or "LaTeX/KaTeX"
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
        density_instruction = "Rule: DENSITY = EXTREME. Goal: Extract 20-50+ cards per chunk. Cover EVERY distinct fact, number, and mechanism."

    highlight_instruction = ""
    if enable_highlighting:
        highlight_instruction = "Rule: Use bold (**text**) to highlight the most high-yield keywords/associations in the Answer."
        
    custom_instruction_str = ""
    if custom_prompt:
        custom_instruction_str = f"10. USER OVERRIDE/ADDITION: {custom_prompt}"

    # Formatting Mode Instructions
    if formatting_mode == "Basic + MathJax":
        formatting_instruction = "Rule: Use plain text with MathJax for math/chemistry. Use \\\\( ... \\\\) for inline math and \\\\[ ... \\\\] for block math. Example: \\\\(H_2O\\\\), \\\\(\\\\frac{1}{2}\\\\). No Markdown. Works with default Anki."
    elif formatting_mode == "Legacy LaTeX":
        formatting_instruction = "Rule: Use Anki's legacy LaTeX format with [latex]...[/latex] tags for math. Example: [latex]H_2O[/latex], [latex]\\\\frac{1}{2}[/latex]. Use plain text otherwise."
    else:  # Default: Markdown
        formatting_instruction = "Rule: Use Markdown for text formatting (bold with **text**, italics with *text*). For math/chemistry, use HTML tags (e.g., <sup>, <sub>). Do NOT use LaTeX."

    system_instruction = f"""You are a world-class Anki flashcard creator that helps students create flashcards that help them remember facts, concepts, and ideas from videos. You will be given a video or document or snippet.
    
    Identify key high-level concepts and ideas presented, including relevant equations. If the content is math or physics-heavy, focus on concepts. If the content isn't heavy on concepts, focus on facts. Use your own knowledge to flesh out any additional details (e.g., relevant facts, dates, and equations) to ensure the flashcards are self-contained.

    Rules:
    1. Formatting: {formatting_instruction}
    2. CSV Structure: "Front"|"Back". Use a pipe | as a delimiter. WARNING: You MUST enclose EVERY field in double quotes. If a field contains a double quote, escape it by doubling it (" -> "").
    3. Completeness: EVERY card MUST have a Question (Front) AND an Answer (Back). Do not generate headers.
    4. Strictness: Output ONLY the CSV content. No code fences. One card per line.
    
    
    
    Custom Preferences:
    5. {length_instruction}
    6. {density_instruction}
    7. {highlight_instruction}
    {custom_instruction_str}
    """


    try:
        if provider == "google":
            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.2,
                max_output_tokens=65536,
            )
            response = _generate_with_retry(model_name, text_chunk, config, fallback_to_flash_lite=True)
            text_resp = response.text
        elif provider == "openrouter":
            text_resp = _generate_with_openrouter(model_name, system_instruction, text_chunk)
        else:
             return "Error: Invalid Provider Selected"
        
        # Clean up response if it contains markdown code blocks
        text = text_resp.strip()
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

# Keep older alias for compatibility if needed, or update app.py
process_chunk_with_gemini = lambda *args, **kwargs: process_chunk(*args, provider="google", **kwargs)

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
    """Sorts a list of filenames logically. Supports Google and OpenRouter."""
    prompt = f"""Sort the following list of filenames in the most logical chronological or numerical order (e.g. Lecture 1 before Lecture 2, Chapter 1 before 10).
    
    Input List:
    {file_names}
    
    Output Strict JSON List of strings (sorted):
    ["file1.pdf", "file2.pdf", ...]
    """

    try:
        import json
        if "/" in model_name:
            # OpenRouter
            system_instruction = "You are a File Organizer. Output strictly valid JSON."
            resp_text = _generate_with_openrouter(model_name, system_instruction, prompt)
        else:
            # Google
            response = _generate_with_retry(
                model_name,
                prompt,
                types.GenerateContentConfig(response_mime_type="application/json", temperature=0.0),
                fallback_to_flash_lite=False 
            )
            resp_text = response.text
            
        sorted_list = json.loads(resp_text)
        if len(sorted_list) == len(file_names):
            return sorted_list
        return file_names
    except:
        return file_names

def generate_chapter_summary(text_chunk: str, model_name: str = "gemma-3-27b-it") -> str:
    """Generates a brief summary of a chapter. Supports Google and OpenRouter."""
    input_text = text_chunk[:30000] 
    
    prompt = f"Summarize the following medical text in 3-5 concise sentences. Focus on high-yield pathologies and mechanisms.\n\nText:\n{input_text}"
    
    try:
        if "/" in model_name:
            # OpenRouter
            system_instruction = "You are a Medical Text Summarizer. Be concise and focus on high-yield medical facts."
            return _generate_with_openrouter(model_name, system_instruction, prompt)
        else:
            # Google/Gemini
            response = _generate_with_retry(
                model_name,
                prompt,
                types.GenerateContentConfig(temperature=0.2),
                fallback_to_flash_lite=True
            )
            return response.text
    except Exception as e:
        return f"Summary failed: {str(e)}"

def generate_full_summary(chapter_summaries: list[str], model_name: str = "gemma-3-27b-it") -> str:
    """Aggregates chapter summaries into a document abstract. Supports Google and OpenRouter."""
    joined_summaries = "\n- ".join(chapter_summaries)
    prompt = f"Create a coherent summary/abstract of the entire document based on these chapter summaries:\n\n- {joined_summaries}"
    
    try:
        if "/" in model_name:
            # OpenRouter
            system_instruction = "You are a Medical Literature Abstractor."
            return _generate_with_openrouter(model_name, system_instruction, prompt)
        else:
            # Google
            response = _generate_with_retry(
                model_name,
                prompt,
                types.GenerateContentConfig(temperature=0.2),
                fallback_to_flash_lite=True
            )
            return response.text
    except Exception as e:
        return f"Full summary failed: {str(e)}"
