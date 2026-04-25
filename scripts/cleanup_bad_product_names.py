import argparse
import re
from typing import Optional

from sqlalchemy import select

from app.db import SessionLocal
from app.db import SessionLocal, models


BAD_MARKERS = [
    "НОВИНК",
    "NEW",
    "смесителей (латунь)",
]

SERIES_PREFIX_RE = re.compile(
    r"\b[A-Z]\d{2,3}(?:-\d{1,3})?\s+смесителей\s+\(латунь\)\s*(?:35mm)?\b",
    re.IGNORECASE,
)

SKU_RE = re.compile(r"\b([A-Z]\d{3,}-\d{1,3}[A-Z]?)\b")

TITLE_START_RE = re.compile(
    r"(Смеситель|Душевая система|Встраиваемый|Термостатическ|Гигиеническ)",
    re.IGNORECASE,
)

CYRILLIC_WORD_RE = re.compile(r"[А-Яа-яЁё]{4,}")
DIMENSION_HEAVY_RE = re.compile(r"[Ø\d±xхX/.()-]{6,}")


def is_usable_clean_name(sku: str, cleaned: str) -> bool:
    if not cleaned:
        return False

    value = cleaned.strip()

    # must be longer than just SKU
    if value.upper() == sku.upper():
        return False

    tail = value[len(sku) :].strip() if value.upper().startswith(sku.upper()) else value

    if not tail:
        return False

    # reject too short/truncated tails
    if len(tail) < 12:
        return False

    # reject obvious truncations
    bad_endings = (
        "для р",
        "термостатическа",
        "встраиваемый гиг",
        "смеситель для",
        "душевая систе",
    )
    if tail.lower().endswith(bad_endings):
        return False

    # must contain at least one decent Cyrillic word
    if not CYRILLIC_WORD_RE.search(tail):
        return False

    # reject dimension-heavy / drawing text
    if "ø" in tail.lower():
        return False

    digit_count = sum(ch.isdigit() for ch in tail)
    letter_count = sum(ch.isalpha() for ch in tail)
    if digit_count > 0 and digit_count >= letter_count:
        return False

    # reject broken OCR garbage with too many spaced single chars
    if re.search(r"(?:\b\w\b[\s.]+){4,}", tail):
        return False

    return True


def is_suspicious_name(name: str) -> bool:
    if not name:
        return False

    upper_name = name.upper()

    if any(marker.upper() in upper_name for marker in BAD_MARKERS):
        return True

    skus = SKU_RE.findall(name)
    if len(set(skus)) >= 2:
        return True

    if len(name) > 80:
        return True

    return False


def clean_name(sku: str, name: str) -> Optional[str]:
    if not name:
        return None

    original = re.sub(r"\s+", " ", name).strip()
    cleaned = original

    # remove promo words
    cleaned = re.sub(r"\bNEW\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bНОВИНКА\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bНОВИНКИ\b", " ", cleaned, flags=re.IGNORECASE)

    # remove series fragments anywhere in string
    cleaned = SERIES_PREFIX_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # find all SKUs
    sku_matches = list(SKU_RE.finditer(cleaned))
    if not sku_matches:
        return None

    # find this product SKU
    main_match = None
    for m in sku_matches:
        if m.group(1).upper() == sku.upper():
            main_match = m
            break

    if not main_match:
        return None

    tail = cleaned[main_match.end() :].strip()

    # if another SKU appears right after, cut before it
    next_skus = list(SKU_RE.finditer(tail))
    if next_skus:
        tail = tail[: next_skus[0].start()].strip()

    # if title keyword exists, start from it
    title_match = TITLE_START_RE.search(tail)
    if title_match:
        tail = tail[title_match.start() :].strip()

    # remove obvious junk at the beginning
    tail = re.sub(r"^[\-\–\—,:;./\s]+", "", tail).strip()

    # final normalization
    cleaned = f"{sku} {tail}".strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if cleaned == original:
        return None

    if not is_usable_clean_name(sku, cleaned):
        return None

    return cleaned


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--brand", required=False, help="Brand filter, e.g. GAPPO")
    parser.add_argument("--commit", action="store_true", help="Apply changes to DB")
    args = parser.parse_args()

    session = SessionLocal()
    try:
        stmt = select(models.Product)

        if args.brand:
            stmt = stmt.where(models.Product.brand.ilike(args.brand))

        products = session.execute(stmt).scalars().all()

        suspicious = 0
        changed = 0

        for product in products:
            sku = (product.sku or "").strip()
            name = (product.name or "").strip()

            if not sku or not name:
                continue

            if not is_suspicious_name(name):
                continue

            suspicious += 1
            new_name = clean_name(sku, name)

            if not new_name or new_name == name:
                continue

            changed += 1

            print("=" * 80)
            print(f"SKU:      {sku}")
            print(f"OLD NAME: {name}")
            print(f"NEW NAME: {new_name}")
            print("REASON:   cleaned suspicious imported title")

            if args.commit:
                product.name = new_name

        if args.commit and changed > 0:
            session.commit()
            print("\nCommitted changes to DB.")
        elif not args.commit:
            print("\nDry run only. Use --commit to apply changes.")

        print("\nSUMMARY")
        print(f"Suspicious found: {suspicious}")
        print(f"Names changed:    {changed}")

    finally:
        session.close()


if __name__ == "__main__":
    main()
