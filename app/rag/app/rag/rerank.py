"""
Lexical helpers reused from the legacy RAG.
Kept small and dependency-free for both product and document rerank steps.
"""

from __future__ import annotations

import re
from typing import Set


def _normalize_token(token: str) -> str:
    if len(token) <= 4:
        return token

    for suf in (
        "ами",
        "ями",
        "ого",
        "ему",
        "ому",
        "ее",
        "ие",
        "ые",
        "ая",
        "яя",
        "ое",
        "еи",
        "ий",
        "ый",
        "ой",
        "ам",
        "ям",
        "ах",
        "ях",
        "ом",
        "ем",
        "ою",
        "ею",
        "a",
        "я",
        "у",
        "ю",
        "е",
        "и",
        "ы",
        "о",
    ):
        if token.endswith(suf) and len(token) - len(suf) >= 4:
            return token[: -len(suf)]
    return token


def tokens_ru(text: str) -> Set[str]:
    text = (text or "").lower()
    text = re.sub(r"[^0-9a-zа-яё\\s]+", " ", text)
    parts = [p for p in text.split() if p]
    return {_normalize_token(p) for p in parts}


def lexical_overlap(query: str, text: str) -> int:
    return len(tokens_ru(query) & tokens_ru(text))


def jaccard_similarity(a: str, b: str) -> float:
    wa = tokens_ru(a)
    wb = tokens_ru(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)
