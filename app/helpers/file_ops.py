# ==========================================
# app/helpers/file_ops.py
# save-state updated 202512172036
# ==========================================

import json
import os
from typing import Any, Dict, List
from datetime import datetime
from app.helpers.json_safe import json_safe  # updated import

DATA_FILE = os.path.join(os.path.dirname(__file__), '../../data/journals.json')

def load_data(file_path: str = DATA_FILE) -> List[Dict[str, Any]]:
    """Safely load JSON data, return empty list if file missing or invalid"""
    if not os.path.exists(file_path):
        return []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # Flatten one-level nested lists
        if data and isinstance(data[0], list):
            data = [item for sublist in data for item in sublist]
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, IOError):
        return []

def save_data(entries: List[Dict[str, Any]], file_path: str = DATA_FILE) -> None:
    """Safely save JSON list; normalizes non-JSON types"""
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(
                json_safe(entries),
                f,
                ensure_ascii=False,
                indent=2
            )
    except IOError as e:
        raise RuntimeError(f"Failed to save data to {file_path}: {e}")

def append_entry(entry: Dict[str, Any], file_path: str = DATA_FILE) -> None:
    # Hard stop: never journal crisis entries
    # IMPORTANT:
    # Crisis-flagged entries must never be written to journals.json.
    # They are recorded exclusively via crisis_recorder.py.

    if entry.get("nlp", {}).get("crisis_flag") is True:
        return

    data = load_data(file_path)
    data.append(entry)
    save_data(data, file_path)


# ------------------ Feedback helpers ------------------ #

def get_feedback_file() -> str:
    """
    Return feedback file path with 6-hour timestamp window.
    Creates file and directories if missing.
    """
    now = datetime.utcnow()
    window = now.hour // 6  # 0: 00-05, 1: 06-11, 2: 12-17, 3: 18-23
    timestamp = now.strftime("%Y%m%d") + f"_{window}"
    file_path = os.path.join(os.path.dirname(__file__), f"../../data/feedback_{timestamp}.json")

    path_obj = os.path.abspath(file_path)
    os.makedirs(os.path.dirname(path_obj), exist_ok=True)
    if not os.path.exists(path_obj):
        # Initialize empty JSON array
        with open(path_obj, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)
    return path_obj

def ensure_feedback_file(file_path: str = None) -> str:
    """
    Ensure feedback file exists.
    If no path is given, uses timestamped 6-hour window file.
    Returns the path to use.
    """
    if file_path is None:
        file_path = get_feedback_file()
    elif not os.path.exists(file_path):
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump([], f, ensure_ascii=False, indent=2)
    return file_path
