from __future__ import annotations

import re
from typing import Optional

SERIES_TITLE_PATTERN = re.compile(
    r"([A-ZА-Я][A-ZА-Я0-9-]*)\s+(?:Серия|серия|СЕРИЯ)\s+(.*?)(?:\s+стр\.|$)",
    re.IGNORECASE,
)

CATEGORY_PATTERN = re.compile(
    r"^(.*?)(?:смесители?|дозаторы?|аксессуары?|комплектующие?)",
    re.IGNORECASE,
)


def extract_series_title(text: str) -> Optional[str]:
    """Extract series title from page text."""
    match = SERIES_TITLE_PATTERN.search(text)
    if match:
        series_code = match.group(1).strip()
        description = match.group(2).strip()
        description = re.sub(r"\s+стр\.\s*\d+.*$", "", description, flags=re.IGNORECASE)
        return f"{series_code} {description}".strip()

    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for line in lines[:10]:
        match = CATEGORY_PATTERN.search(line)
        if match:
            category = match.group(0).strip()
            if 5 < len(category) < 100:
                return category

    return None
