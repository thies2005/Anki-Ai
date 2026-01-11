"""
Utils package for Anki AI.

Contains modules for:
- llm_handler: AI provider integration (Google Gemini, OpenRouter)
- pdf_processor: PDF text extraction and chunking
- data_processing: CSV parsing and AnkiConnect integration
- rag: Simple vector store for document retrieval
"""

from utils.llm_handler import (
    configure_gemini,
    configure_openrouter,
    process_chunk,
    get_chat_response,
    get_embedding,
    generate_chapter_summary,
    generate_full_summary,
    detect_chapters_in_text,
    split_text_by_chapters,
    is_openrouter_model,
)

from utils.pdf_processor import (
    extract_text_from_pdf,
    clean_text,
    recursive_character_text_splitter,
    get_pdf_front_matter,
    extract_chapters_from_pdf,
)

from utils.data_processing import (
    robust_csv_parse,
    push_card_to_anki,
    deduplicate_cards,
)

from utils.rag import SimpleVectorStore

__all__ = [
    # LLM Handler
    "configure_gemini",
    "configure_openrouter", 
    "process_chunk",
    "get_chat_response",
    "get_embedding",
    "generate_chapter_summary",
    "generate_full_summary",
    "detect_chapters_in_text",
    "split_text_by_chapters",
    "is_openrouter_model",
    # PDF Processor
    "extract_text_from_pdf",
    "clean_text",
    "recursive_character_text_splitter",
    "get_pdf_front_matter",
    "extract_chapters_from_pdf",
    # Data Processing
    "robust_csv_parse",
    "push_card_to_anki",
    "deduplicate_cards",
    # RAG
    "SimpleVectorStore",
]
