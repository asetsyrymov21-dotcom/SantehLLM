from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import settings


def get_gappo_card(article: str | None) -> dict[str, Any] | None:
    if not article:
        return None
    return _load_by_article().get(article)


def search_gappo_cards(query: str, *, limit: int = 5) -> list[dict[str, Any]]:
    normalized = _normalize(query)
    wants_mixer = any(marker in normalized for marker in ("смес", "кран", "smes", "kran"))
    wants_kitchen = any(marker in normalized for marker in ("кух", "мойк", "kukh", "kitchen"))
    wants_black = any(marker in normalized for marker in ("чер", "chern", "black"))

    if not any((wants_mixer, wants_kitchen, wants_black)):
        return []

    matches: list[tuple[int, int, str, dict[str, Any]]] = []
    for article, card in _load_by_article().items():
        name = _normalize(card.get("name") or "")
        category = _normalize(card.get("category") or "")
        color = _normalize(card.get("color") or "")

        if wants_mixer and "смес" not in name:
            continue
        if wants_kitchen and "кух" not in name:
            continue
        if wants_black and "чер" not in color:
            continue

        score = 0
        if wants_mixer and "смес" in name:
            score += 5
        if wants_kitchen and "кух" in name:
            score += 5
        if wants_black and "чер" in color:
            score += 5
        if "смес" in category:
            score += 2
        if card.get("quality", {}).get("confidence") == "high":
            score += 1

        page = int((card.get("source") or {}).get("page") or 99999)
        matches.append((score, page, article, card))

    matches.sort(key=lambda item: (-item[0], item[1], item[2]))
    return [card for _, _, _, card in matches[:limit]]


def format_gappo_card(card: dict[str, Any]) -> str:
    lines = [
        f"Точная карточка GAPPO: {card.get('article') or 'N/A'} — {card.get('name') or 'N/A'}",
        f"Категория: {card.get('category') or 'N/A'}",
    ]

    fields = [
        ("Цвет", "color"),
        ("Материал", "material"),
        ("Тип установки", "install_type"),
        ("Подводка", "connection"),
        ("Размер упаковки", "package_size"),
        ("Фасовка", "packing"),
        ("Штук в упаковке", "items_per_pack"),
        ("Штук в коробке", "items_per_carton"),
    ]
    for label, key in fields:
        value = card.get(key)
        if value not in (None, "", []):
            lines.append(f"{label}: {value}")

    source = card.get("source") or {}
    page = source.get("page")
    if page:
        lines.append(f"Источник: каталог GAPPO 2026, страница PDF {page}.")

    quality = card.get("quality") or {}
    confidence = quality.get("confidence")
    issues = quality.get("issues") or []
    if confidence:
        lines.append(f"Качество извлечения: {confidence}.")
    if confidence == "medium" or issues:
        warning = "Данные требуют проверки"
        if page:
            warning += f" по странице PDF: {page}"
        warning += "."
        lines.append(warning)
        if issues:
            lines.append("Предупреждения: " + "; ".join(str(issue) for issue in issues))

    return "\n".join(lines)


def _normalize(text: str) -> str:
    return " ".join((text or "").lower().replace("ё", "е").split())


@lru_cache(maxsize=1)
def _load_by_article() -> dict[str, dict[str, Any]]:
    path = Path(settings.gappo_indexes_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        return {}

    data = json.loads(path.read_text(encoding="utf-8"))
    by_article = data.get("by_article") or {}
    return {str(article): card for article, card in by_article.items()}
