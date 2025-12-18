# ==========================================
# file: core/nlp/anchors.py
# save-state updated 202512171405 (date and time formatted as follows: YYYYMMDDhhmm)
# ==========================================

import re
from typing import Pattern, List, Set

# ========================
# Crisis phrases
# ========================
_CRISIS_PHRASES = [
    "kill myself", "want to die", "end my life", "suicide", "can't go on",
    "tired of living", "wish i were dead", "end it all", "ultimate price", "unalive", "sewerslide"
]

# ========================
# Public functions
# ========================
def get_crisis_phrases() -> List[str]:
    """Return canonical list of crisis phrases for the pipeline."""
    return _CRISIS_PHRASES
