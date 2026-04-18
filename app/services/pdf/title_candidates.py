import re


def _extract_title_candidates(
    block_text: str, main_sku: str, page_title: str = ""
) -> list[str]:
    candidates: list[str] = []

    normalized = re.sub(r"\s+", " ", block_text).strip()

    sku_pos = normalized.upper().find(main_sku.upper())
    tail = normalized[sku_pos + len(main_sku) :].strip() if sku_pos >= 0 else normalized

    def _clean_phrase(phrase: str) -> str:
        phrase = re.sub(r"\s+", " ", phrase).strip(" -,:;")

        phrase = re.split(
            r"\b(Материал|Тип крепления|Гибкая подводка|Размер упаковки|Габариты|Вес|Подключение|Комплектация|Монтаж)\b",
            phrase,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip(" -,:;")

        phrase = re.split(
            r"\b[A-Z]\d{3,}(?:-\d{1,3}[A-Z]?)?\b",
            phrase,
            maxsplit=1,
        )[
            0
        ].strip(" -,:;")

        phrase = re.sub(r"\b\d{2,4}\b(?=\s+\d+-функц)", "", phrase)

        # Cut numeric garbage only at the END of an otherwise valid title:
        # "... душа 420"
        # "... душ 34 44 122"
        # "... душ 34-44 122"
        phrase = re.sub(r"(?:\s+\d{2,4}(?:-\d{1,4})?){1,3}\s*$", "", phrase)

        phrase = re.sub(r"\s+", " ", phrase).strip(" -,:;")
        return phrase

    # Strong leading phrase after SKU
    if tail:
        leading_phrase = re.split(
            r"\b(Материал|Тип крепления|Гибкая подводка|Размер упаковки|Габариты|Вес|Подключение|Комплектация|Монтаж)\b",
            tail,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip(" -,:;")

        leading_phrase = _clean_phrase(leading_phrase)

        if leading_phrase and len(leading_phrase) <= 80:
            candidates.append(f"{main_sku} {leading_phrase}")

    # Keep short tail as weak fallback only
    if tail:
        short_tail = _clean_phrase(tail[:120])
        if short_tail:
            candidates.append(f"{main_sku} {short_tail}")

    product_type_patterns = [
        r"(Встраиваемый\s+гигиенический\s+душ\b[\sА-Яа-яA-Za-z-]*)",
        r"(Встраиваемый\s+смеситель\s+для\s+[А-Яа-яA-Za-z\s-]+)",
        r"(Смеситель\s+напольный\s+для\s+[А-Яа-яA-Za-z\s-]+)",
        r"(Душевая\s+система\s+для\s+[А-Яа-яA-Za-z\s-]+)",
        r"(Душевая\s+система\b[\sА-Яа-яA-Za-z-]*)",
        r"(Смеситель\s+для\s+[А-Яа-яA-Za-z\s-]+)",
        r"(Смеситель\b[\sА-Яа-яA-Za-z-]*)",
        r"(Дозатор\b[\sА-Яа-яA-Za-z-]*)",
        r"(Излив\b[\sА-Яа-яA-Za-z-]*)",
        r"(Лейка\b[\sА-Яа-яA-Za-z-]*)",
    ]

    for pattern in product_type_patterns:
        for match in re.finditer(pattern, tail, flags=re.IGNORECASE):
            phrase = _clean_phrase(match.group(1))

            if phrase and len(phrase.split()) >= 1:
                candidates.append(f"{main_sku} {phrase}")

    if page_title:
        short_page_title = re.sub(r"\s+", " ", page_title).strip()
        short_page_title = short_page_title[:60].strip(" -,:;")
        if short_page_title:
            candidates.append(f"{main_sku} {short_page_title}")

    deduped: list[str] = []
    seen: set[str] = set()
    for c in candidates:
        key = c.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(c)

    return deduped
