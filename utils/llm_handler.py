from google import genai
from google.genai import types
import os
import openai
import time
import re
import json
import logging

# Configure logging
logger = logging.getLogger(__name__)


def configure_gemini(api_key: str, fallback_keys: list = None):
    """
    Configures the Gemini API.
    Returns: dictionary containing 'primary' and 'fallbacks' clients.
    """
    clients = {
        "primary": None,
        "fallbacks": []
    }
    
    if api_key and api_key.strip():
        clients["primary"] = genai.Client(api_key=api_key)
        
    if fallback_keys:
        for key in fallback_keys:
            if key and key.strip():
                try:
                    clients["fallbacks"].append(genai.Client(api_key=key))
                except Exception as e:
                    logger.warning(f"Failed to configure fallback key: {e}")
    return clients

def configure_openrouter(api_key: str):
    """
    Configures the OpenRouter API.
    Returns: OpenRouter client instance or None.
    """
    if api_key and api_key.strip():
        return openai.OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
    return None

# Constants for rate limiting
RATE_LIMIT_GEMMA = 2.0  # 30 RPM
RATE_LIMIT_FLASH_LITE = 6.0  # 10 RPM
RATE_LIMIT_FREE = 3.0  # 20 RPM
RATE_LIMIT_DEFAULT = 1.0

# Model fallback lists
GOOGLE_FALLBACK_MODELS = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-3-flash", "gemma-3-27b-it"]
OPENROUTER_FALLBACK_MODELS = [
    "xiaomi/mimo-v2-flash:free",
    "google/gemini-2.0-flash-exp:free",
    "mistralai/devstral-2512:free",
    "qwen/qwen3-coder:free",
    "google/gemma-3-27b-it:free"
]

# Context limits
CONTEXT_LIMIT_DEFAULT = 100000
CONTEXT_LIMIT_XIAOMI = 200000
MAX_SAMPLE_TEXT = 1000000
MAX_TOC_TEXT = 30000
MAX_SUMMARY_TEXT = 30000
MAX_VECTOR_STORE_CHUNKS = 5000
MIN_CHUNK_LENGTH = 50

def rate_limit_delay(model_name: str) -> None:
    """Enforces rate limits based on model type."""
    if "gemma" in model_name:
        delay = RATE_LIMIT_GEMMA
    elif "flash-lite" in model_name:
        delay = RATE_LIMIT_FLASH_LITE
    elif "free" in model_name:
        delay = RATE_LIMIT_FREE
    else:
        delay = RATE_LIMIT_DEFAULT
    time.sleep(delay)

from tenacity import (
    retry, 
    stop_after_attempt, 
    wait_exponential, 
    retry_if_exception_type,
    before_sleep_log
)

def _retry_on_api_error(exception):
    """Return True if exception is a 429 or 503 error."""
    msg = str(exception).lower()
    return "429" in msg or "resource_exhausted" in msg or "503" in msg

@retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    before_sleep=before_sleep_log(logger, logging.WARNING)
)
def _generate_with_retry(model_name: str, contents, config, client_config: dict, fallback_to_flash_lite: bool = True):
    """
    Centralized generation with Key Rotation (Primary -> Fallbacks) and Model Fallback.
    """
    primary_client = client_config.get("primary")
    fallback_clients = client_config.get("fallbacks", [])
    
    if not primary_client:
         raise ValueError("Google API Key not configured.")
        
    rate_limit_delay(model_name)
    
    # Ensure current model is tried first, then the others
    models_to_try = [model_name]
    if fallback_to_flash_lite:
        for m in GOOGLE_FALLBACK_MODELS:
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
        # Try Primary Key
        try:
            return attempt(primary_client, current_model)
        except Exception as e:
            errors.append(f"Model {current_model} (Primary) Error: {e}")
            
            # Key Rotation for fallback clients
            if _retry_on_api_error(e):
                for idx, client in enumerate(fallback_clients):
                    try:
                        time.sleep(1) 
                        return attempt(client, current_model)
                    except Exception as e2:
                        errors.append(f"Model {current_model} (Fallback {idx+1}) Error: {e2}")
                        continue
            
    # If we get here, trigger Tenacity retry by raising exception
    raise Exception(f"All attempts failed. Errors: {'; '.join(errors)}")


def _generate_with_openrouter(model_name: str, system_instruction: str, user_content: str, client):
    """Generates content using OpenRouter with 429 fallback to other free models."""
    if not client:
        raise ValueError("OpenRouter API Key not configured.")

    # Try the requested model first, then fallbacks
    models_to_try = [model_name]
    for m in OPENROUTER_FALLBACK_MODELS:
        if m not in models_to_try:
            models_to_try.append(m)

    errors = []
    for current_model in models_to_try:
        try:
            rate_limit_delay(current_model)
            if errors:
                time.sleep(1) # Extra pause between different model attempts
            response = client.chat.completions.create(
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

def get_chat_response(messages: list, context: str, provider: str, model_name: str, google_client=None, openrouter_client=None, direct_chat: bool = False) -> str:
    """
    Handles chat interaction.
    If direct_chat=True, it chats with the model directly without document context.
    messages: list of {"role": "user"|"assistant", "content": "..."}
    """
    if direct_chat:
        system_prompt = "You are a helpful and intelligent AI assistant. Answer the user's questions clearly and accurately."
    else:
        context_limit = CONTEXT_LIMIT_XIAOMI if "xiaomi" in model_name.lower() else CONTEXT_LIMIT_DEFAULT
        system_prompt = f"""You are a helpful Medical Assistant AI. 
        Answer questions based strictly on the provided medical context.
        
        Context:
        {context[:context_limit]} 
        
        (Context truncated to {context_limit} chars for safety)
        """
    
    if provider == "google":
        client_config = google_client
        if not client_config or not client_config.get("primary"): return "Error: Google Client not configured."
        
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
            response = _generate_with_retry(model_name, gemini_hist, config, client_config, fallback_to_flash_lite=True)
            return response.text
        except Exception as e:
            return f"Chat Error: {e}"

    elif provider == "openrouter":
        if not openrouter_client: return "Error: OpenRouter Client not configured."
        
        rate_limit_delay(model_name)
        
        # OpenRouter/OpenAI Format
        # Prepend system prompt to messages
        full_messages = [{"role": "system", "content": system_prompt}] + messages
        
        try:
            response = openrouter_client.chat.completions.create(
                model=model_name,
                messages=full_messages,
                temperature=0.7
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"Chat Error: {e}"
    
    return "Error: Invalid Provider"

def get_embedding(text: str, provider: str = "google", model_name: str = "text-embedding-004", google_client=None) -> list:
    """Generates an embedding vector for the given text."""
    try:
        if provider == "google":
            client_config = google_client
            if not client_config or not client_config.get("primary"): return []
            primary_client = client_config["primary"]
            
            result = primary_client.models.embed_content(
                model=model_name,
                contents=text
            )
            return result.embeddings[0].values
        elif provider == "openrouter":
            # OpenRouter might support embeddings, but it's variable.
            return [] 
    except Exception as e:
        print(f"Embedding check failed: {e}")
        return []


def process_chunk(text_chunk: str, google_client=None, openrouter_client=None, provider: str = "google", model_name: str = "gemini-3-flash", card_length: str = "Medium (Standard)", card_density: str = "Normal", enable_highlighting: bool = False, custom_prompt: str = "", formatting_mode: str = "Markdown/HTML", existing_topics: list[str] = None) -> str:
    """
    Sends a text chunk to the selected Provider/Model and retrieves Anki CSV cards.
    formatting_mode: "Plain Text", "Markdown/HTML", or "LaTeX/KaTeX"
    existing_topics: list of titles/questions already generated to avoid duplicates.
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
        # Normal density - balanced card generation
        density_instruction = "Rule: DENSITY = NORMAL. Generate cards for main ideas and key supporting details. Avoid trivial facts. Target 5-15 cards per chunk."

    highlight_instruction = ""
    
    # Formatting Mode Instructions
    if formatting_mode == "Basic + MathJax":
        formatting_instruction = "Rule: Use ONLY HTML tags for formatting. For bold use <b>text</b>, for italics use <i>text</i>, for superscript use <sup>text</sup>, for subscript use <sub>text</sub>. Do NOT use Markdown (no ** or *). Do NOT use LaTeX delimiters like $ or \\\\(. Keep it simple HTML that works in default Anki Basic cards."
        if enable_highlighting:
            highlight_instruction = "Rule: Use <b>text</b> to highlight the most high-yield keywords/associations in the Answer."
    elif formatting_mode == "Legacy LaTeX":
        formatting_instruction = "Rule: Use Anki's legacy LaTeX format with [latex]...[/latex] tags for math. Example: [latex]H_2O[/latex], [latex]\\\\frac{1}{2}[/latex]. Use plain text or simple HTML otherwise."
        if enable_highlighting:
            highlight_instruction = "Rule: Use <b>text</b> to highlight the most high-yield keywords in the Answer."
    else:  # Default: Markdown
        formatting_instruction = "Rule: Use Markdown for text formatting (bold with **text**, italics with *text*). For math/chemistry, use HTML tags (e.g., <sup>, <sub>). Do NOT use LaTeX."
        if enable_highlighting:
            highlight_instruction = "Rule: Use bold (**text**) to highlight the most high-yield keywords/associations in the Answer."

    custom_instruction_str = ""
    if custom_prompt:
        custom_instruction_str = f"8. USER OVERRIDE/ADDITION: {custom_prompt}"
    
    anti_dupe_instruction = ""
    if existing_topics:
        # Optimization: Only show very recent topics to guide style, rely on post-processing for strict dedupe
        # showing last 10 instead of 50
        topics_str = "; ".join(existing_topics[-10:]) 
        anti_dupe_instruction = f"9. ANTI-DUPLICATE: The following concepts have ALREADY been generated. Do NOT create cards for them: [{topics_str}]"
    
    system_instruction = f"""You are a world-class Anki flashcard creator that helps students create flashcards that help them remember facts, concepts, and ideas from videos. You will be given a video or document or snippet.
    
    Identify key high-level concepts and ideas presented, including relevant equations. If the content is math or physics-heavy, focus on concepts. If the content isn't heavy on concepts, focus on facts. Use your own knowledge to flesh out any additional details (e.g., relevant facts, dates, and equations) to ensure the flashcards are self-contained.

    Rules:
    1. Formatting: {formatting_instruction}
    2. TSV Structure: "Front"[TAB]"Back". Use a TAB character as the delimiter (not pipe, not comma). Enclose EVERY field in double quotes. If a field contains a double quote, escape it by doubling it (" -> "").
    3. Completeness: EVERY card MUST have a Question (Front) AND an Answer (Back). Do not generate headers.
    4. Strictness: Output ONLY the TSV content. No code fences. One card per line.
    5. NO DUPLICATES: Do NOT generate duplicate or near-duplicate questions. Each card must test a UNIQUE concept. If you've already created a card about a topic, do NOT rephrase the same question.
    
    Custom Preferences:
    6. {length_instruction}
    7. {density_instruction}
    8. {highlight_instruction}
    {custom_instruction_str}
    {anti_dupe_instruction}
    """


    try:
        if provider == "google":
            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.2,
                max_output_tokens=65536,
            )
            response = _generate_with_retry(model_name, text_chunk, config, google_client, fallback_to_flash_lite=True)
            text_resp = response.text
        elif provider == "openrouter":
            text_resp = _generate_with_openrouter(model_name, system_instruction, text_chunk, openrouter_client)
        else:
             return "Error: Invalid Provider Selected"
        
        # Clean up response if it contains markdown code blocks
        text = text_resp.strip()
        
        # Remove markdown code blocks if present
        if "```" in text:
            match = re.search(r"```(?:csv|tsv)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
            if match:
                text = match.group(1).strip()
        
        # Additional cleanup: Remove lines that don't look like CSV/TSV data
        lines = text.splitlines()
        clean_lines = []
        for line in lines:
            line = line.strip()
            if not line: continue
            # Basic heuristic: accept lines with quotes and delimiter
            if '"' in line and ("\t" in line or "|" in line):
                 clean_lines.append(line)
        
        if clean_lines:
            text = "\n".join(clean_lines)
            
        return text
    except Exception as e:
        return f"Error processing chunk: {str(e)}"

# Legacy alias removal or update if strictly needed, but better to update calls.
# process_chunk_with_gemini = ... (Removing to encourage proper usage)

def analyze_toc_with_gemini(toc_text: str, google_client, model_name: str = "gemini-2.5-flash-lite") -> str:
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
    3. **CRITICAL**: The 'page' must be the **PDF page number** (integer) found in the text. if the text says "Page 123", output 123.
    4. If page numbers are missing or not parseable, return an empty list.
    
    Text:
    {toc_text[:MAX_TOC_TEXT]} 
    """

    try:
        response = _generate_with_retry(
            model_name, 
            prompt, 
            types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1),
            google_client,
            fallback_to_flash_lite=False
        )
        return response.text
    except Exception as e:
        return f"Error analyzing TOC: {str(e)}"

def sort_files_with_gemini(file_names: list[str], google_client=None, openrouter_client=None, model_name: str = "gemma-3-27b-it") -> list[str]:
    """Sorts a list of filenames logically. Supports Google and OpenRouter."""
    prompt = f"""Sort the following list of filenames in the most logical chronological or numerical order (e.g. Lecture 1 before Lecture 2, Chapter 1 before 10).
    
    Input List:
    {file_names}
    
    Output Strict JSON List of strings (sorted):
    ["file1.pdf", "file2.pdf", ...]
    """

    try:
        if "/" in model_name:
            # OpenRouter
            system_instruction = "You are a File Organizer. Output strictly valid JSON."
            resp_text = _generate_with_openrouter(model_name, system_instruction, prompt, openrouter_client)
        else:
            # Google
            response = _generate_with_retry(
                model_name,
                prompt,
                types.GenerateContentConfig(response_mime_type="application/json", temperature=0.0),
                google_client,
                fallback_to_flash_lite=False 
            )
            resp_text = response.text
            
        sorted_list = json.loads(resp_text)
        if len(sorted_list) == len(file_names):
            return sorted_list
        return file_names
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Failed to sort files with AI: {e}")
        return file_names
    except Exception as e:
        logger.error(f"Unexpected error sorting files: {e}")
        return file_names

def generate_chapter_summary(text_chunk: str, google_client=None, openrouter_client=None, model_name: str = "gemma-3-27b-it") -> str:
    """Generates a brief summary of a chapter. Supports Google and OpenRouter."""
    input_text = text_chunk[:MAX_SUMMARY_TEXT]
    
    prompt = f"Summarize the following medical text in 3-5 concise sentences. Focus on high-yield pathologies and mechanisms.\n\nText:\n{input_text}"
    
    try:
        if "/" in model_name:
            # OpenRouter
            system_instruction = "You are a Medical Text Summarizer. Be concise and focus on high-yield medical facts."
            return _generate_with_openrouter(model_name, system_instruction, prompt, openrouter_client)
        else:
            # Google/Gemini
            response = _generate_with_retry(
                model_name,
                prompt,
                types.GenerateContentConfig(temperature=0.2),
                google_client,
                fallback_to_flash_lite=True
            )
            return response.text
    except Exception as e:
        return f"Summary failed: {str(e)}"

def generate_full_summary(chapter_summaries: list[str], google_client=None, openrouter_client=None, model_name: str = "gemma-3-27b-it") -> str:
    """Aggregates chapter summaries into a document abstract. Supports Google and OpenRouter."""
    joined_summaries = "\n- ".join(chapter_summaries)
    prompt = f"Create a coherent summary/abstract of the entire document based on these chapter summaries:\n\n- {joined_summaries}"
    
    try:
        if "/" in model_name:
            # OpenRouter
            system_instruction = "You are a Medical Literature Abstractor."
            return _generate_with_openrouter(model_name, system_instruction, prompt, openrouter_client)
        else:
            # Google
            response = _generate_with_retry(
                model_name,
                prompt,
                types.GenerateContentConfig(temperature=0.2),
                google_client,
                fallback_to_flash_lite=True
            )
            return response.text
    except Exception as e:
        return f"Full summary failed: {str(e)}"

def detect_chapters_in_text(text: str, file_name: str, google_client=None, openrouter_client=None, model_name: str = "gemma-3-27b-it") -> list:
    """
    Detects chapters within a text document using AI.
    Returns: [{"title": "Chapter 1 Name", "description": "..."}, ...]
    """
    # Use up to 1M chars for complete analysis
    sample_text = text[:MAX_SAMPLE_TEXT]
    
    prompt = f"""Analyze this document text and identify distinct chapters or major sections.

Document: {file_name}

Text Sample:
{sample_text}

Output STRICT JSON array of chapters with:
[
  {{"title": "Chapter 1: Introduction", "description": "brief 1-sentence summary"}},
  {{"title": "Chapter 2: Main Topic", "description": "brief 1-sentence summary"}},
  ...
]

Rules:
1. Look for clear chapter headings, section titles, or major topic transitions
2. If no clear chapters exist, return an empty array []
3. Minimum 2 chapters to qualify (otherwise return [])
4. Maximum 20 chapters
5. Output ONLY valid JSON, no explanations
"""

    try:
        if is_openrouter_model(model_name):
            system_instruction = "You are a Document Chapter Analyzer. Output strictly valid JSON."
            resp_text = _generate_with_openrouter(model_name, system_instruction, prompt, openrouter_client)
        else:
            response = _generate_with_retry(
                model_name,
                prompt,
                types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1),
                google_client,
                fallback_to_flash_lite=True
            )
            resp_text = response.text
            
        try:
            chapters = extract_json_from_text(resp_text)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse chapter JSON: {e}")
            chapters = []
        
        return chapters if isinstance(chapters, list) and len(chapters) >= 2 else []
    except Exception as e:
        logger.warning(f"Chapter detection failed: {e}")
        return []  # If detection fails, treat as single document

def is_openrouter_model(model_name: str) -> bool:
    """Check if model name indicates OpenRouter provider."""
    return "/" in model_name


def extract_json_from_text(text: str) -> list:
    """Safely extracts JSON from a string, handling markdown code blocks."""
    text = text.strip()
    
    # 1. Try to find markdown JSON block
    match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if match:
        text = match.group(1).strip()
        
    # 2. If valid JSON, return it
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
        
    # 3. Try to find start [ and end ]
    start = text.find('[')
    end = text.rfind(']')
    
    if start != -1 and end != -1 and end > start:
        json_str = text[start:end+1]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
            
    return []


def split_text_by_chapters(text: str, chapters: list) -> list:
    """
    Attempts to split text based on detected chapter titles.
    Returns: [{"title": "...", "text": "..."}, ...]
    """
    if not chapters:
        return []
    
    # Simple heuristic: search for chapter titles in the text and split
    import re
    chapter_splits = []
    
    for i, chapter in enumerate(chapters):
        title = chapter.get("title", "")
        # Try to find this title in the text
        # Look for variations: with/without "Chapter X:", case-insensitive
        pattern = re.escape(title[:30])  # Use first 30 chars to be flexible
        matches = list(re.finditer(pattern, text, re.IGNORECASE))
        
        if matches:
            start_pos = matches[0].start()
            # Find end position (start of next chapter or end of text)
            if i < len(chapters) - 1:
                next_title = chapters[i + 1].get("title", "")
                next_pattern = re.escape(next_title[:30])
                next_matches = list(re.finditer(next_pattern, text[start_pos + 100:], re.IGNORECASE))
                if next_matches:
                    end_pos = start_pos + 100 + next_matches[0].start()
                else:
                    end_pos = len(text)
            else:
                end_pos = len(text)
            
            chapter_splits.append({
                "title": title,
                "text": text[start_pos:end_pos]
            })
    
    # If we couldn't split reliably, return empty to fall back to whole document
    if len(chapter_splits) < len(chapters) // 2:
        return []
    
    return chapter_splits
