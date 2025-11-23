"""
app/helpers/file_ops.py

Provides file loading, saving, and ensuring feedback storage functionality.
"""

import json
import os
from typing import Any, Dict, List, Optional

# Default file paths (can be overridden)
DATA_FILE = os.path.join(os.path.dirname(__file__), '../../data/journals.json')
FEEDBACK_FILE = os.path.join(os.path.dirname(__file__), '../../data/feedback.json')

def normalize_emotion_profile(profile: Dict[str, float]) -> Dict[str, float]:
    total = sum(profile.values())
    if total > 0:
        return {k: v / total for k, v in profile.items()}
    return profile


def load_data(file_path: str = DATA_FILE) -> List[Dict[str, Any]]:
    """
    Safely load JSON data from a file.
    Returns an empty list if file doesn't exist or is empty.
    """
    if not os.path.exists(file_path):
        return []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            else:
                return []
    except (json.JSONDecodeError, IOError):
        return []


def save_data(entry: Dict[str, Any], file_path: str = DATA_FILE) -> None:
    """
    Append a new entry to a JSON file safely.
    Ensures the file always contains a list of entries.
    """
    data = load_data(file_path)
    data.append(entry)
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except IOError as e:
        raise RuntimeError(f"Failed to save data to {file_path}: {e}")


def ensure_feedback_file(file_path: str = FEEDBACK_FILE) -> None:
    """
    Ensures the feedback file exists and is initialized as a JSON list.
    """
    if not os.path.exists(file_path):
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump([], f, ensure_ascii=False, indent=2)
        except IOError as e:
            raise RuntimeError(f"Failed to create feedback file {file_path}: {e}")
