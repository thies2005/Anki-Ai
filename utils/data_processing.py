
import pandas as pd
import csv
from io import StringIO
import requests
import json
import os
import logging

logger = logging.getLogger(__name__)

# Constants
ANKICONNECT_TIMEOUT = 5  # seconds

def deduplicate_cards(new_cards: pd.DataFrame, existing_questions: list[str]) -> pd.DataFrame:
    """
    Filters out cards where the 'Front' is similar to existing questions.
    Uses simple exact match or normalized match for now to avoid overhead.
    """
    if new_cards.empty or not existing_questions:
        return new_cards
        
    # Normalize existing for comparison (lowercase, stripped)
    existing_set = {q.lower().strip() for q in existing_questions}
    
    # Filter
    unique_indices = []
    for idx, row in new_cards.iterrows():
        front = str(row['Front']).lower().strip()
        if front not in existing_set:
            unique_indices.append(idx)
            # Add to local set to avoid dupes within the same batch
            existing_set.add(front)
            
    return new_cards.loc[unique_indices]

def push_card_to_anki(front: str, back: str, deck: str, tags: list = None) -> bool:
    """
    Pushes a single card to Anki via AnkiConnect.
    Returns True if successful.
    """
    if tags is None: tags = []
    
    note = {
        "deckName": deck,
        "modelName": "Basic",
        "fields": {
            "Front": front,
            "Back": back
        },
        "options": {
            "allowDuplicate": False,
            "duplicateScope": "deck"
        },
        "tags": tags
    }
    
    payload = {
        "action": "addNote",
        "version": 6,
        "params": {
            "note": note
        }
    }
    
    try:
        anki_url = os.getenv("ANKI_CONNECT_URL", "http://localhost:8765")
        response = requests.post(anki_url, json=payload, timeout=ANKICONNECT_TIMEOUT)
        result = response.json()
        if result.get("error") is None:
            return True
        logger.warning(f"AnkiConnect error: {result.get('error')}")
        return False
    except requests.exceptions.Timeout:
        logger.warning("AnkiConnect request timed out")
        return False
    except requests.exceptions.ConnectionError:
        logger.warning("Could not connect to AnkiConnect - is Anki running?")
        return False
    except Exception as e:
        logger.error(f"Unexpected error pushing to Anki: {e}")
        return False

def robust_csv_parse(csv_text: str) -> pd.DataFrame:
    """
    Parses LLM-generated CSV/TSV text more robustly than pd.read_csv.
    Handles manual quote fixing and bad lines.
    Assumes TSV (Tab Separated) as per prompt instructions.
    """
    data = []
    lines = csv_text.strip().splitlines()
    
    for line in lines:
        line = line.strip()
        if not line: continue
        
        # heuristic: if it doesn't look like a TSV line, skip or try to fix
        if "\t" not in line:
            # Maybe it used | or comma?
            if "|" in line:
                parts = line.split("|")
            elif "," in line:
                # Naive comma split, mostly for fail-safe
                parts = line.split(",")
            else:
                continue
        else:
            parts = line.split("\t")
            
        if len(parts) < 2:
            continue
            
        # Clean quotes
        front = parts[0].strip()
        back = parts[1].strip()
        
        # Remove surrounding quotes if they exist
        if front.startswith('"') and front.endswith('"'):
            front = front[1:-1].replace('""', '"')
        if back.startswith('"') and back.endswith('"'):
            back = back[1:-1].replace('""', '"')
            
        # Combine remaining parts into back if there were extra tabs (e.g. inside content, though rare with quotes)
        # But per prompt, we asked for 2 columns.
        if len(parts) > 2:
            # Re-join the rest just in case
            extra = "\t".join(parts[2:])
            back = f"{back} {extra}".strip()
            if back.startswith('"') and back.endswith('"'):
                 back = back[1:-1].replace('""', '"')

        data.append({"Front": front, "Back": back})
        
    return pd.DataFrame(data)
