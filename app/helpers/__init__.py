# ==========================================
# app.helpers.__init__.py
# Save-state: 202602171541 (YYYYMMDDhhmm)
# Module initialization for helper utilities.
# This file ensures that helper modules can be imported cleanly from the `app.helpers` package.
# ==========================================

# Import commonly used helpers for easier access
from .file_ops import load_data, save_data, ensure_feedback_file
from .entry_similarity import cosine_similarity, deterministic_mean, safe_load_embedding
from .top_matches import find_top_matches
from .json_safe import json_safe