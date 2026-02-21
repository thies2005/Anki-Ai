"""
PDF processing utilities for Anki AI.

Provides functions for extracting text from PDFs, cleaning text,
and splitting documents into manageable chunks.
"""

import fitz  # PyMuPDF
import re
import unicodedata
import logging

logger = logging.getLogger(__name__)

# Constants
DEFAULT_CHUNK_SIZE = 10000
DEFAULT_OVERLAP = 200
TOC_PAGE_LIMIT = 50

def _open_pdf_stream(pdf_stream):
    """
    Helper to open a PDF stream efficiently.
    Tries to use zero-copy access (getbuffer) if available to avoid
    duplicating the file content in memory.
    """
    try:
        pdf_stream.seek(0)
        if hasattr(pdf_stream, "getbuffer"):
            return fitz.open(stream=pdf_stream.getbuffer(), filetype="pdf")
    except Exception:
        pass

    # Fallback to reading the full stream
    pdf_stream.seek(0)
    return fitz.open(stream=pdf_stream.read(), filetype="pdf")

def extract_text_from_pdf(pdf_stream) -> str:
    """
    Extracts all text from a PDF file stream.
    """
    doc = None
    try:
        doc = _open_pdf_stream(pdf_stream)
        text = []
        for page in doc:
            text.append(page.get_text())
        raw_text = "\n".join(text)
        return unicodedata.normalize('NFC', raw_text)
    except Exception as e:
        raise ValueError(f"Error reading PDF: {e}")
    finally:
        # Ensure the document is properly closed to prevent resource leaks
        if doc is not None:
            try:
                doc.close()
            except Exception:
                pass  # Already closed or invalid

def get_pdf_front_matter(pdf_stream, page_limit: int = 50) -> str:
    """Extracts text from the first 'page_limit' pages."""
    doc = None
    try:
        doc = _open_pdf_stream(pdf_stream)
        text = []
        limit = min(page_limit, doc.page_count)
        for i in range(limit):
            text.append(doc.load_page(i).get_text())
        raw_text = "\n".join(text)
        return unicodedata.normalize('NFC', raw_text)
    except Exception as e:
        return ""
    finally:
        if doc is not None:
            try:
                doc.close()
            except Exception:
                pass

def extract_chapters_from_pdf(pdf_stream, ai_extracted_toc: list = None) -> list[dict]:
    """
    Extracts text per chapter based on PDF outline or AI-provided TOC.
    Returns: list of dicts {'title': str, 'text': str}
    """
    doc = None

    def get_page_offset(doc):
        # Scan first 50 pages to find one labeled "1"
        for i in range(min(50, doc.page_count)):
            if doc.load_page(i).get_label() == "1":
                return i
        return 0

    try:
        doc = _open_pdf_stream(pdf_stream)

        toc = []
        if ai_extracted_toc:
            # Convert AI TOC [{'title':..., 'page':...}] to fitz format [[lvl, title, page, ...]]
            # Fitz expects: [level, title, page, dest]
            # We assume level 1 for all api results
            for item in ai_extracted_toc:
                # AI pages are likely 1-indexed printed numbers.
                # We treat them as 1-indexed for consistency with fitz .get_toc() output which usually uses 1-based page numbers for display,
                # BUT fitz `get_toc(simple=True)` returns 1-based page numbers usually.
                # Actually PyMuPDF `get_toc()` returns [[lvl, title, page, ...]]. The 'page' IS 1-based.
                toc.append([1, item.get('title', 'Chapter'), item.get('page', 1)])
        else:
            toc = doc.get_toc()

        # If no TOC, return entire doc as one chapter
        if not toc:
            text = []
            for page in doc:
                text.append(page.get_text())
            return [{"title": "Full Document", "text": "\n".join(text)}]

        chapters = []
        page_count = doc.page_count

        # Calculate offset for Roman numeral prefaces
        pdf_offset = get_page_offset(doc)

        for i in range(len(toc)):
            item = toc[i]
            level = item[0]
            title = item[1]
            start_page = item[2]
            # Ignore remaining fields like 'dest' which might not exist for AI extracted TOC or simple TOCs

            # Determine end page
            if i < len(toc) - 1:
                next_start = toc[i+1][2]
                # If next chapter starts on same page, current range is effectively distinct?
                # Or usually next ch starts on next page.
                # We'll assume exclusive range [start, next_start)
                end_page = next_start - 1
            else:
                end_page = page_count

            # Adjust for 0-based indexing AND PDF internal offset
            # TOC pages are 1-based relative to the "logical" Page 1
            p_start = max(0, pdf_offset + (start_page - 1))

            # For end page, we apply similar logic if it's based on logical numbering
            # Note: end_page calc above was (next_start - 1).
            # So next_start matches next logical page.
            p_end = max(0, pdf_offset + (end_page - 1))

            # Safety clamp
            if p_end >= page_count:
               p_end = page_count - 1

            # If the next chapter starts on the same page, we might duplicate text
            # if we just grab the whole page.
            # However, precise text extraction per coordinate is hard.
            # We will grab the whole page logic for now as it's standard for this level of granularity.

            chapter_text_list = []
            if p_start <= p_end:
                for p_idx in range(p_start, p_end + 1):
                    chapter_text_list.append(doc.load_page(p_idx).get_text())

            raw_text = "\n".join(chapter_text_list)
            chapters.append({
                "title": title,
                "text": unicodedata.normalize('NFC', raw_text)
            })

        return chapters

    except Exception as e:
        raise ValueError(f"Error extracting chapters from PDF: {e}")
    finally:
        # Ensure the document is properly closed to prevent resource leaks
        if doc is not None:
            try:
                doc.close()
            except Exception:
                pass

def clean_text(text: str) -> str:
    """
    Cleans extra whitespace while preserving some structure if needed.
    """
    # Normalize whitespace: replace multiple spaces/newlines with single space
    # or keep clear paragraph breaks?
    # For LLM processing, single spaces are usually fine unless strict formatting is needed.
    # However, Medical texts might have tables or lists.
    # Let's stick to simple normalization for now.
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def recursive_character_text_splitter(text: str, chunk_size: int = 10000, overlap: int = 200) -> list[str]:
    """
    Splits text into chunks of approximately chunk_size with overlap.
    Tries to split on sentence boundaries or spaces.
    """
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + chunk_size, text_len)
        
        if end == text_len:
            chunks.append(text[start:end])
            break

        # Try to find a suitable split point
        # Prioritize: Period+Space, then Space
        
        # Look in the last 10% of the window for a split point
        lookback = min(1000, chunk_size // 5)
        search_start = max(start, end - lookback)
        chunk_window = text[search_start:end]

        # Regex for sentence ending
        sentence_end = list(re.finditer(r'[.!?]\s', chunk_window))
        
        split_point = -1
        if sentence_end:
            split_point = search_start + sentence_end[-1].end()
        else:
            # Fallback: look for space
            last_space = chunk_window.rfind(' ')
            if last_space != -1:
                split_point = search_start + last_space + 1
        
        if split_point == -1 or split_point <= start:
            # If no good split point found, force split at max size
            split_point = end
        
        chunks.append(text[start:split_point])
        
        # Move start pointer, accounting for overlap
        # The next chunk starts at split_point - overlap
        # ensuring we don't go backwards or get stuck
        next_start = split_point - overlap
        
        # If overlap pushes us back to or before current start, just advance
        if next_start <= start:
            next_start = start + 1 # Ensure strictly forward progress, at least 1 char
            
        start = next_start

    return chunks
