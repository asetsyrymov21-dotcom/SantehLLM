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
