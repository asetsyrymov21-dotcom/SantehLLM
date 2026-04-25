"""
PDF Data Extractor for enrichment pipeline.

Extracts and structures product data from PDF catalog pages.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Optional

from app.services.pdf.normalizer import normalize_text, normalize_sku
from .models import PdfProductMatch

logger = logging.getLogger(__name__)


class PdfDataExtractor:
    """Extracts structured product data from PDF pages."""

    def __init__(self):
        self._extraction_cache: dict[tuple[str, int], dict[str, Any]] = {}

    def extract_page_data(
        self, pdf_path: Path | str, page_number: int
    ) -> dict[str, Any]:
        """
        Extract all relevant data from a PDF page.

        Returns:
            Dict with:
            - title: Page/product title
            - subtitle: Secondary description
            - skus: List of SKUs found on page
            - tables: Extracted tables
            - raw_text: Full page text
        """
        cache_key = (str(pdf_path), page_number)

        if cache_key in self._extraction_cache:
            return self._extraction_cache[cache_key]

        from app.services.pdf.extractor import (
            extract_text_from_page,
            extract_table_from_page,
        )

        try:
            raw_text = extract_text_from_page(pdf_path, page_number)
            tables = extract_table_from_page(pdf_path, page_number)

            # Parse title from text
            title = self._extract_title(raw_text)
            subtitle = self._extract_subtitle(raw_text, title)

            # Extract all SKUs from page
            skus = self._extract_all_skus(raw_text, tables)

            result = {
                "title": title,
                "subtitle": subtitle,
                "skus": skus,
                "tables": tables,
                "raw_text": raw_text[:1000] if raw_text else "",  # Limit for cache
            }

            self._extraction_cache[cache_key] = result
            return result

        except Exception as e:
            logger.warning(f"Failed to extract page {page_number}: {e}")
            return {
                "title": None,
                "subtitle": None,
                "skus": [],
                "tables": [],
                "raw_text": "",
            }

    def _extract_title(self, text: str) -> Optional[str]:
        """Extract product title from page text."""
        if not text:
            return None

        lines = [line.strip() for line in text.split("\n") if line.strip()]

        # Common title patterns in GAPPO catalogs
        title_patterns = [
            r"^([^\n]{10,80})\s+стр\.\s*\d+",  # "Product Name стр. 42"
            r"^([A-Z]\d+[^\n]{0,50})\s+Серия",  # "G52 Серия смесителей"
        ]

        text_normalized = normalize_text(text)

        for pattern in title_patterns:
            match = re.search(pattern, text_normalized, re.IGNORECASE | re.MULTILINE)
            if match:
                title = match.group(1).strip()
                if len(title) > 5:
                    return title

        # Heuristic: first substantial line that's not noise
        for line in lines[:15]:
            line = normalize_text(line)

            if self._is_noise_line(line):
                continue

            if len(line) < 10:
                continue

            if len(line) > 150:
                continue

            # Should contain some letters
            if not re.search(r"[A-Za-zА-Яа-я]{3,}", line):
                continue

            return line

        return None

    def _extract_subtitle(self, text: str, title: Optional[str]) -> Optional[str]:
        """Extract subtitle/description from page text."""
        if not text:
            return None

        lines = [line.strip() for line in text.split("\n") if line.strip()]

        # Find line after title
        title_found = False
        for line in lines[:20]:
            line = normalize_text(line)

            if title_found:
                if self._is_noise_line(line):
                    continue
                if len(line) < 5 or len(line) > 200:
                    continue
                return line

            if line == title or (title and title in line):
                title_found = True

        return None

    def _extract_all_skus(
        self, text: str, tables: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Extract all SKUs with their row data from page.

        Returns:
            List of dicts with 'sku' and row data
        """
        skus = []
        seen_skus: set[str] = set()

        # Extract from tables first (more reliable)
        for row in tables:
            for key, value in row.items():
                if not value:
                    continue

                value_str = str(value).strip()
                normalized = normalize_sku(value_str)

                if self._looks_like_sku(normalized) and normalized not in seen_skus:
                    seen_skus.add(normalized)
                    row_data = dict(row)
                    row_data["sku"] = normalized
                    skus.append(row_data)

        # Also search in text for SKUs not in tables
        text_skus = self._extract_skus_from_text(text)
        for sku in text_skus:
            if sku not in seen_skus:
                seen_skus.add(sku)
                skus.append({"sku": sku})

        return skus

    def _extract_skus_from_text(self, text: str) -> list[str]:
        """Extract SKU patterns from raw text."""
        if not text:
            return []

        # Common SKU patterns in GAPPO catalogs
        patterns = [
            r"\b([A-Z]\d{4,}(?:-\d{1,3}[A-Z0-9]?)?)\b",  # G10101, G10101-13, G10101-13B
            r"\b([A-Z]{2,3}\d{3,}(?:-[A-Z0-9]+)?)\b",  # AB123, XYZ456-AB
        ]

        found = []
        seen: set[str] = set()

        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                sku = match.group(1).upper()
                normalized = normalize_sku(sku)

                if normalized not in seen and self._looks_like_sku(normalized):
                    seen.add(normalized)
                    found.append(normalized)

        return found

    def _looks_like_sku(self, value: str) -> bool:
        """Check if value looks like a valid SKU."""
        if not value or len(value) < 4:
            return False

        # Must contain letters and digits
        has_letter = bool(re.search(r"[A-Z]", value))
        has_digit = bool(re.search(r"\d", value))

        return has_letter and has_digit

    def _is_noise_line(self, line: str) -> bool:
        """Check if line is noise (not a title)."""
        noise_patterns = [
            r"^\s*\d+\s*$",  # Just numbers
            r"^стр\.?\s*\d+",  # Page numbers
            r"^page\s*\d+",
            r"^каталог",
            r"^смесители",
            r"^www\.",
            r"^http",
            r"^\.\.\.",
            r"^---*$",
        ]

        line_lower = line.lower()

        for pattern in noise_patterns:
            if re.search(pattern, line_lower):
                return True

        # Too many numbers relative to letters
        digits = sum(c.isdigit() for c in line)
        letters = sum(c.isalpha() for c in line)

        if digits > letters * 2 and digits > 5:
            return True

        return False

    def build_description_from_row(self, row: dict[str, Any]) -> str:
        """Build human-readable description from table row."""
        parts = []

        # Map common column names to readable labels
        label_map = {
            "size": "Размер",
            "размер": "Размер",
            "diameter": "Диаметр",
            "диаметр": "Диаметр",
            "dn": "DN",
            "nominal_pressure": "Номинальное давление",
            "раб_давление_бар": "Рабочее давление",
            "working_pressure_bar": "Рабочее давление (бар)",
            "раб_температура_c": "Рабочая температура",
            "working_temperature_c": "Температура (°C)",
            "package_m": "Упаковка",
            "упак_м": "Упаковка",
            "material": "Материал",
            "материал": "Материал",
            "color": "Цвет",
            "цвет": "Цвет",
        }

        for key, value in row.items():
            if key in ("sku", "артикул") or not value:
                continue

            label = label_map.get(key, key.replace("_", " ").title())
            parts.append(f"{label}: {value}")

        return "\n".join(parts)


def extract_candidate_from_page_text(
    sku: str,
    page_number: int,
    raw_text: str,
    pdf_name: str = "",
) -> Optional[PdfProductMatch]:
    """Extract product data from saved page text (no live PDF access)."""
    from app.services.pdf.normalizer import normalize_sku
    import re

    if not raw_text:
        logger.info("[EXTRACT sku=%s page=%s] EMPTY TEXT", sku, page_number)
        return None

    normalized_sku = normalize_sku(sku)
    text_upper = raw_text.upper()

    logger.info(
        "[EXTRACT sku=%s page=%s] text_len=%s",
        normalized_sku,
        page_number,
        len(raw_text),
    )

    sku_in_text = normalized_sku in text_upper

    if not sku_in_text:
        no_dash_sku = normalized_sku.replace("-", "")
        no_dash_match = no_dash_sku in text_upper.replace("-", "")
        logger.info(
            "[EXTRACT sku=%s page=%s] SKU NOT FOUND (no-dash=%s)",
            normalized_sku,
            page_number,
            no_dash_match,
        )
        if not no_dash_match:
            return None
    else:
        logger.info(
            "[EXTRACT sku=%s page=%s] SKU FOUND",
            normalized_sku,
            page_number,
        )

    title = _extract_title_from_saved_text(raw_text, normalized_sku)

    if not title:
        logger.info(
            "[EXTRACT sku=%s page=%s] TITLE NOT FOUND",
            normalized_sku,
            page_number,
        )
        return None

    logger.info(
        "[EXTRACT sku=%s page=%s] SUCCESS title='%s'",
        normalized_sku,
        page_number,
        title[:100],
    )

    return PdfProductMatch(
        sku=normalized_sku,
        pdf_title=title,
        pdf_description=None,
        source_file=pdf_name,
        source_page=page_number,
        additional_attributes={},
    )


REFERENCE_PAGE_RE = re.compile(
    r"(?:стр\.?|cтр\.?|стр)\s*(\d{1,3})",
    re.IGNORECASE,
)


def extract_referenced_pages_for_token(
    page_text: str,
    token: str,
    window: int = 400,
) -> list[int]:
    if not page_text or not token:
        logger.info("[REF token=%s] EMPTY INPUT", token)
        return []

    token_norm = normalize_sku(token)
    text_norm = normalize_sku(page_text)

    logger.info(
        "[REF token=%s] search start (window=%s, text_len=%s)",
        token_norm,
        window,
        len(text_norm),
    )

    refs: list[int] = []

    matches = list(re.finditer(re.escape(token_norm), text_norm, re.IGNORECASE))
    logger.info("[REF token=%s] token_matches=%s", token_norm, len(matches))

    for match in matches:
        start = max(0, match.start() - window)
        end = min(len(text_norm), match.end() + window)
        chunk = text_norm[start:end]

        chunk_refs = []
        for ref_match in REFERENCE_PAGE_RE.finditer(chunk):
            try:
                page_no = int(ref_match.group(1))
                refs.append(page_no)
                chunk_refs.append(page_no)
            except ValueError:
                continue

        logger.info(
            "[REF token=%s] match_pos=%s:%s refs=%s",
            token_norm,
            match.start(),
            match.end(),
            chunk_refs,
        )

    seen = set()
    unique_refs: list[int] = []
    for page_no in refs:
        if page_no not in seen:
            seen.add(page_no)
            unique_refs.append(page_no)

    logger.info("[REF token=%s] unique_refs=%s", token_norm, unique_refs)
    return unique_refs


def extract_referenced_pages_for_sku(page_text: str, sku: str) -> list[int]:
    """Find referenced detail pages near full SKU."""
    return extract_referenced_pages_for_token(page_text, sku)


def derive_reference_tokens(sku: str) -> list[str]:
    """
    Build fallback series-like tokens for overview pages.

    Example:
        G2007-3 -> G07-3
        G2007-9 -> G07-9
    """
    sku_norm = normalize_sku(sku)
    tokens: list[str] = []

    m = re.match(r"^G\d*(\d{2}-\d+)$", sku_norm)
    if m:
        tokens.append(f"G{m.group(1)}")

    return tokens


def _is_bad_single_line_title_candidate(candidate: str) -> bool:
    import re

    if not candidate:
        return True

    c_upper = candidate.upper()

    # overview/reference markers
    if "СТР" in c_upper or "CTPAH" in c_upper or "ЁЄЁ" in c_upper:
        return True

    # too many SKU-like tokens => probably overview list, not title
    sku_tokens = re.findall(r"\bG\d{2,}(?:-\d+[A-Z0-9]?)?\b", c_upper)
    if len(sku_tokens) >= 2:
        return True

    # starts with long SKU-ish sequence
    if re.match(r"^(?:\d+\s+)?(?:G\d{2,}(?:-\d+[A-Z0-9]?)?\s+){2,}", c_upper):
        return True

    return False


def _extract_raw_candidate_block_from_saved_text(
    text: str,
    sku: str,
    window_before: int = 400,
    window_after: int = 400,
) -> Optional[str]:
    """Extract raw text block around exact SKU position with smart boundaries."""
    import re

    if not text or not sku:
        return None

    text_upper = text.upper()
    sku_upper = sku.upper()

    # Try exact SKU match first
    pos = text_upper.find(sku_upper)

    # Try without dashes if exact match fails
    if pos == -1:
        no_dash_sku = sku_upper.replace("-", "")
        no_dash_text = text_upper.replace("-", "")
        pos = no_dash_text.find(no_dash_sku)

        if pos != -1:
            # Map position back to original text - find approximate location
            # by searching around the matched position
            search_start = max(0, pos - len(sku_upper))
            search_end = min(len(text), pos + len(sku_upper) + 10)
            pos = text_upper.find(sku_upper[0], search_start)
            if pos == -1 or pos >= search_end:
                pos = search_start

    if pos == -1:
        return None

    start = max(0, pos - window_before)
    end = min(len(text), pos + len(sku) + window_after)
    block = text[start:end]

    # Clean whitespace but preserve structure
    block = re.sub(r"\s+", " ", block).strip()

    return block


def _cleanup_title_candidate(raw_block: str, sku: str) -> Optional[str]:
    """Clean raw OCR block to human-readable product title."""
    import re

    if not raw_block:
        return None

    # Work with original case for better title preservation
    candidate = raw_block.strip(" -|,;:")

    # Cut at first specification marker
    spec_markers = [
        r"\d{1,2}/\d{1,2}\s*(?:мм|mm)",  # 1/2 мм, 3/4 mm
        r"(?:упак|уп\.|pack).*?\d+\s*(?:м|шт|pcs)",
        r"(?:материал|material)",
        r"(?:раб\s*давл|working\s*press)",
        r"(?:темп|temp)",
        r"DN\s*\d+",
        r"Bar",
        r"bar",
        r"Высота",
        r"Диаметр",
        r"Вес",
        r"Размер",
    ]

    for marker in spec_markers:
        match = re.search(marker, candidate, re.IGNORECASE)
        if match:
            cut_pos = match.start()
            if cut_pos > 15:  # Only cut if we'd leave something meaningful
                candidate = candidate[:cut_pos].strip(" -|,;:")
                break

    # Remove numeric-only trailing sequences
    candidate = re.sub(r"\s+\d[\d\s\.,]*$", "", candidate).strip()

    # Clean up excessive SKU mentions (keep only first)
    sku_pattern = r"\bG\d{4,}(?:-\d+[A-Z0-9]?)?\b"
    sku_matches = list(re.finditer(sku_pattern, candidate, re.IGNORECASE))
    if len(sku_matches) > 1:
        # Keep text up to start of second SKU
        candidate = candidate[: sku_matches[1].start()].strip(" -|,;:")

    # Final length validation
    if len(candidate) < 10 or len(candidate) > 150:
        return None

    # Reject if mostly numbers
    digits = sum(c.isdigit() for c in candidate)
    if digits > len(candidate) * 0.4:
        return None

    return candidate


def _extract_title_from_saved_text(text: str, sku: str) -> Optional[str]:
    """Extract product title from saved page text using two-stage approach."""
    import re

    if not text:
        logger.info("[TITLE sku=%s] EMPTY TEXT", sku)
        return None

    lines = [l.strip() for l in text.split("\n") if l.strip()]
    logger.info("[TITLE sku=%s] total_lines=%s", sku, len(lines))

    # ========================================
    # STAGE 1: Single-line collapsed OCR mode
    # ========================================
    if len(lines) == 1:
        single = lines[0]
        upper = single.upper()
        logger.info("[TITLE sku=%s] single-line mode", sku)

        # --- 1A: Exact SKU block extraction ---
        raw_block = _extract_raw_candidate_block_from_saved_text(single, sku)
        logger.info(
            "[TITLE sku=%s] exact-SKU raw_block=%s",
            sku,
            raw_block[:80] if raw_block else "NONE",
        )

        if raw_block:
            cleaned = _cleanup_title_candidate(raw_block, sku)
            logger.info(
                "[TITLE sku=%s] exact-SKU cleaned=%s",
                sku,
                cleaned[:80] if cleaned else "REJECTED",
            )

            if cleaned and not _is_bad_single_line_title_candidate(cleaned):
                logger.info(
                    "[TITLE sku=%s] exact-SKU SUCCESS: %s",
                    sku,
                    cleaned[:100],
                )
                return cleaned[:100]
            else:
                logger.info(
                    "[TITLE sku=%s] exact-SKU rejected by cleanup or filter",
                    sku,
                )

        # --- 1B: Series token fallback ---
        series_match = re.match(r"^G\d*(\d{2}-\d+)$", sku.upper())
        series_token = f"G{series_match.group(1)}" if series_match else None

        if series_token:
            raw_block = _extract_raw_candidate_block_from_saved_text(
                single, series_token, window_before=20, window_after=220
            )
            logger.info(
                "[TITLE sku=%s] series-token=%s raw_block=%s",
                sku,
                series_token,
                raw_block[:80] if raw_block else "NONE",
            )

            if raw_block:
                cleaned = _cleanup_title_candidate(raw_block, sku)
                logger.info(
                    "[TITLE sku=%s] series cleaned=%s",
                    sku,
                    cleaned[:80] if cleaned else "REJECTED",
                )

                if cleaned and not _is_bad_single_line_title_candidate(cleaned):
                    logger.info(
                        "[TITLE sku=%s] series-token SUCCESS: %s",
                        sku,
                        cleaned[:100],
                    )
                    return cleaned[:100]
                else:
                    logger.info(
                        "[TITLE sku=%s] series-token rejected by cleanup or filter",
                        sku,
                    )

        logger.info("[TITLE sku=%s] single-line: no valid candidate", sku)
        return None

    # ========================================
    # STAGE 2: Multi-line mode (existing logic)
    # ========================================

    # Pattern 1: Series header above SKU line
    for i, line in enumerate(lines):
        if sku in line.upper():
            logger.info(
                "[TITLE sku=%s] SKU line at index=%s: %s",
                sku,
                i,
                line[:120],
            )

            for j in range(max(0, i - 5), i):
                prev_line = lines[j]
                if "SERIYA" in prev_line.upper() or "CEP" in prev_line.upper():
                    if 5 < len(prev_line) < 100:
                        logger.info(
                            "[TITLE sku=%s] series header: %s",
                            sku,
                            prev_line[:100],
                        )
                        return prev_line[:100]

    # Pattern 2: Product keywords
    product_keywords = [
        "SMESITEL",
        "KRAN",
        "LATUN",
        "NERZ",
        "DUSH",
        "VAL",
        "TRUBA",
        "UGOL",
        "FITING",
        "GIBKA",
    ]

    for idx, line in enumerate(lines[:15]):
        line_upper = line.upper()
        if any(kw in line_upper for kw in product_keywords):
            if 10 < len(line) < 250:
                sku_count = len(re.findall(r"\b[A-Z]\d{3,}\b", line))
                logger.info(
                    "[TITLE sku=%s] keyword line=%s sku_count=%s: %s",
                    sku,
                    idx,
                    sku_count,
                    line[:100],
                )
                if sku_count < 2:
                    logger.info("[TITLE sku=%s] keyword hit", sku)
                    return line[:100]

    # Pattern 3: Page title pattern
    title_match = re.search(
        r"^([A-Z]\d+[^\n]{0,60})\s+CTPAH\.", text, re.MULTILINE | re.IGNORECASE
    )
    if title_match:
        logger.info(
            "[TITLE sku=%s] page-title: %s",
            sku,
            title_match.group(1)[:100],
        )
        return title_match.group(1).strip()[:100]

    # Pattern 4: First substantial line
    for idx, line in enumerate(lines[:10]):
        if len(line) < 10 or len(line) > 200:
            continue

        digits = sum(c.isdigit() for c in line)
        if digits > len(line) * 0.5:
            continue

        if "WWW" in line.upper() or "HTTP" in line.upper():
            continue

        sku_count = len(re.findall(r"\b[A-Z]\d{3,}(?:-\d+)?\b", line))
        if sku_count >= 2:
            continue

        logger.info(
            "[TITLE sku=%s] fallback line=%s: %s",
            sku,
            idx,
            line[:100],
        )
        return line[:100]

    logger.info("[TITLE sku=%s] NO TITLE EXTRACTED", sku)
    return None
