import re
from .classifier import is_valid_sku


def _extract_nearby_page_title(
    full_text: str,
    start_pos: int,
    main_sku: str,
) -> str | None:
    """
    Fallback for cases like page 97 where local block_text contains only
    finish/color text, but the real product title exists nearby in the
    page reading stream.

    Important:
    restrict search to the local SKU segment so titles from neighboring
    product cards do not leak into the current card.
    """
    sku_pattern = re.compile(r"\b([A-Z]\d{3,}(?:-\d{1,3}[A-Z]?)?)\b", re.IGNORECASE)

    matches = [
        m for m in sku_pattern.finditer(full_text) if is_valid_sku(m.group(1).upper())
    ]
    if not matches:
        return None

    prev_pos = 0
    next_pos = len(full_text)

    for i, m in enumerate(matches):
        pos = m.start()
        if pos == start_pos:
            if i > 0:
                prev_pos = matches[i - 1].start()
            if i + 1 < len(matches):
                next_pos = matches[i + 1].start()
            break
        if pos < start_pos:
            prev_pos = pos
        elif pos > start_pos:
            next_pos = pos
            break

    segment_start = max(prev_pos, start_pos - 220)
    segment_end = min(next_pos, start_pos + 220)

    segment = full_text[segment_start:segment_end]
    segment = re.sub(r"\s+", " ", segment).strip()

    if not segment:
        return None

    def _clean_phrase(phrase: str) -> str:
        phrase = re.sub(r"\s+", " ", phrase).strip(" -,:;")
        phrase = re.split(
            r"\b(Материал|Тип крепления|Гибкая подводка|Размер упаковки|Габариты|Вес|Подключение|Комплектация|Монтаж)\b",
            phrase,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip(" -,:;")
        phrase = re.sub(r"\s+", " ", phrase).strip(" -,:;")
        return phrase

    product_type_patterns = [
        r"(Душевая\s+система\s+для\s+[А-Яа-яA-Za-z\s-]+)",
        r"(Душевая\s+система\b[\sА-Яа-яA-Za-z-]*)",
        r"(Смеситель\s+напольный\s+для\s+[А-Яа-яA-Za-z\s-]+)",
        r"(Встраиваемый\s+смеситель\s+для\s+[А-Яа-яA-Za-z\s-]+)",
        r"(Встраиваемый\s+гигиенический\s+душ\b[\sА-Яа-яA-Za-z-]*)",
        r"(Смеситель\s+для\s+[А-Яа-яA-Za-z\s-]+)",
        r"(Смеситель\b[\sА-Яа-яA-Za-z-]*)",
    ]

    candidates: list[tuple[int, str]] = []

    for pattern in product_type_patterns:
        for match in re.finditer(pattern, segment, flags=re.IGNORECASE):
            phrase = _clean_phrase(match.group(1))
            if phrase:
                candidates.append((match.start(), phrase))

    if not candidates:
        return None

    sku_local_pos = start_pos - segment_start

    before = [(pos, phrase) for pos, phrase in candidates if pos <= sku_local_pos]
    if before:
        # Prefer the closest phrase before this SKU
        before.sort(key=lambda item: abs(item[0] - sku_local_pos))
        phrase = before[0][1]
    else:
        # If nothing is before, fall back to closest overall
        candidates.sort(key=lambda item: abs(item[0] - sku_local_pos))
        phrase = candidates[0][1]

    if not phrase:
        return None

    return f"{main_sku} {phrase}"
