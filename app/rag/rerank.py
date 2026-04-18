import re


def tokens_ru(s: str) -> set[str]:
    s = (s or "").lower()
    s = re.sub(r"[^0-9a-zа-яё\s]+", " ", s)
    parts = [p for p in s.split() if p]

    def norm(w: str) -> str:
        if len(w) <= 4:
            return w
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
            "а",
            "я",
            "у",
            "ю",
            "е",
            "и",
            "ы",
            "о",
        ):
            if w.endswith(suf) and len(w) - len(suf) >= 4:
                return w[: -len(suf)]
        return w

    return set(norm(p) for p in parts)


def lexical_overlap(query: str, text: str) -> int:
    return len(tokens_ru(query) & tokens_ru(text))


def jaccard_similarity(a: str, b: str) -> float:
    wa = tokens_ru(a)
    wb = tokens_ru(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)
