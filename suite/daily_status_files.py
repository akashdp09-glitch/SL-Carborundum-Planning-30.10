"""Shared filename-prefix conventions for departmental Daily Status workbooks."""
from __future__ import annotations

import re
from pathlib import Path

# Prefixes are the user's numeric section identifiers. 5 maps to the combined
# Grinding/Cutting stream; internal legacy slot name remains "Grinding".
SECTION_PREFIX_MAP = {
    "1": "Preparation",
    "2": "Mixing",
    "3": "Forming",
    "4": "Firing",
    "5": "Grinding",
    "6": "Packing",
}
SECTION_DISPLAY = {
    "Preparation": "Preparation",
    "Mixing": "Mixing",
    "Forming": "Forming",
    "Firing": "Firing",
    "Grinding": "Grinding / Cutting",
    "Packing": "Packing",
}


def section_from_filename(filename: str) -> str:
    """Infer section from a leading 1..6 followed by punctuation/space/text."""
    stem = Path(str(filename or "")).stem
    match = re.match(r"^\s*([1-6])(?:\D|$)", stem)
    return SECTION_PREFIX_MAP.get(match.group(1), "") if match else ""
