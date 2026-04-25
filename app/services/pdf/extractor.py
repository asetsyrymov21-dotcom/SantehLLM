"""
PDF extractor module for page-by-page content extraction.

Handles large PDFs efficiently by processing one page at a time
without loading entire file into memory.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from contextlib import contextmanager

try:
    import pdfplumber

    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False

from .normalizer import clean_cell_value, normalize_sku, normalize_text

logger = logging.getLogger(__name__)


@dataclass
class ProductBlock:
    """
    Represents a product block extracted from a catalog page.

    Typical structure:
    - title: main product name (e.g., "Труба металлопластиковая")
    - subtitle: description/context (e.g., "для отопления")
    - brand: manufacturer brand
    - page_number: source page in PDF
    - rows: table rows with SKU variants
    """

    title: str
    subtitle: str
    brand: Optional[str]
    page_number: int
    rows: list[dict[str, Any]] = field(default_factory=list)
    source_file: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "title": self.title,
            "subtitle": self.subtitle,
            "brand": self.brand,
            "page_number": self.page_number,
            "rows": self.rows,
            "source_file": self.source_file,
        }


def extract_text_from_page(pdf_path: str | Path, page_number: int) -> str:
    with _open_pdf_page(pdf_path, page_number) as page:
        raw_text = page.extract_text() or ""
        normalized_text = normalize_text(raw_text)

        if page_number == 70:
            raw_preview = raw_text[:500].replace("\n", " ")
            normalized_preview = normalized_text[:500].replace("\n", " ")
            logger.debug("[extractor][page=%s] raw_text=%r", page_number, raw_preview)
            logger.debug(
                "[extractor][page=%s] normalized_text=%r",
                page_number,
                normalized_preview,
            )

        return normalized_text


def extract_table_from_page(
    pdf_path: str | Path,
    page_number: int,
) -> list[dict[str, Any]]:
    """
    Extract tables from specific page as list of dictionaries.

    Args:
        pdf_path: Path to PDF file
        page_number: 1-based page number

    Returns:
        List of rows as dictionaries (header -> value)

    Raises:
        ValueError: If page_number is invalid
        FileNotFoundError: If PDF doesn't exist
    """
    with _open_pdf_page(pdf_path, page_number) as page:
        tables = page.extract_tables()

    if not tables:
        logger.debug("No tables found on page %s", page_number)
        return []

    results: list[dict[str, Any]] = []

    for table_idx, table in enumerate(tables, start=1):
        if not table or len(table) < 2:
            continue

        raw_headers = table[0]
        headers = [_normalize_header(cell) for cell in raw_headers]

        for row_idx, row in enumerate(table[1:], start=2):
            if not row:
                continue

            row_dict: dict[str, Any] = {}
            non_empty_values = 0

            for idx, cell in enumerate(row):
                header = (
                    headers[idx]
                    if idx < len(headers) and headers[idx]
                    else f"col_{idx}"
                )
                value = clean_cell_value(cell)

                if value not in ("", None):
                    non_empty_values += 1

                row_dict[header] = value

            if _is_meaningful_row(row_dict, non_empty_values=non_empty_values):
                results.append(row_dict)
            else:
                logger.debug(
                    "Skipping empty/noisy row on page=%s table=%s row=%s: %s",
                    page_number,
                    table_idx,
                    row_idx,
                    row_dict,
                )

    return results


def extract_product_block_from_page(
    pdf_path: str | Path,
    page_number: int,
    brand_hint: Optional[str] = None,
    source_file: Optional[str] = None,
) -> Optional[ProductBlock]:
    """
    Extract structured product block from a catalog page.

    Expects structure:
    - Title at top (product name)
    - Subtitle below (description)
    - Table with SKU variants

    Args:
        pdf_path: Path to PDF file
        page_number: 1-based page number
        brand_hint: Brand name if known from filename/context
        source_file: Original filename for tracking

    Returns:
        ProductBlock or None if no product data found
    """
    logger.info("Extracting product block from page %s", page_number)

    text = extract_text_from_page(pdf_path, page_number)
    tables = extract_table_from_page(pdf_path, page_number)

    if not text and not tables:
        logger.warning("Page %s: no text or tables found", page_number)
        return None

    lines = _prepare_text_lines(text)
    title, subtitle = _parse_title_subtitle(lines)

    if not title:
        logger.warning("Page %s: no title found", page_number)
        return None

    rows: list[dict[str, Any]] = []
    if tables:
        for table_row in tables:
            row_data = _normalize_table_row(table_row)
            if _row_has_sku(row_data):
                rows.append(row_data)

    if not rows:
        logger.warning("Page %s: no SKU rows found in table", page_number)
        return None

    logger.info("Page %s: found '%s' with %s rows", page_number, title, len(rows))

    return ProductBlock(
        title=title,
        subtitle=subtitle,
        brand=brand_hint,
        page_number=page_number,
        rows=rows,
        source_file=source_file or str(pdf_path),
    )


@contextmanager
def _open_pdf_page(pdf_path: str | Path, page_number: int):
    if not PDFPLUMBER_AVAILABLE:
        raise ImportError("pdfplumber required")

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    with pdfplumber.open(str(pdf_path)) as pdf:
        if page_number < 1 or page_number > len(pdf.pages):
            raise ValueError(
                f"Invalid page {page_number}. PDF has {len(pdf.pages)} pages."
            )

        yield pdf.pages[page_number - 1]


def _normalize_header(cell_value: Any) -> str:
    """Normalize table header text."""
    if not cell_value:
        return ""

    text = str(cell_value).lower().strip()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", "_", text)
    return text.strip("_")


def _prepare_text_lines(text: str) -> list[str]:
    return [normalize_text(line) for line in text.split("\n") if normalize_text(line)]


def _parse_title_subtitle(lines: list[str]) -> tuple[str, str]:
    """
    Extract title and subtitle from page text lines.

    Heuristics:
    - Title: first meaningful non-table-like line near top
    - Subtitle: next meaningful descriptive line
    """
    if not lines:
        return "", ""

    title_idx: Optional[int] = None
    title = ""

    for idx, line in enumerate(lines[:15]):  # only inspect top area of page
        if _looks_like_noise_line(line):
            continue
        if _looks_like_table_row_text(line):
            continue
        if len(line) < 3:
            continue

        title = line
        title_idx = idx
        break

    if title_idx is None:
        return "", ""

    subtitle = ""
    for next_line in lines[title_idx + 1 : title_idx + 6]:
        if _looks_like_noise_line(next_line):
            continue
        if _looks_like_table_row_text(next_line):
            continue
        if len(next_line) > 200:
            continue

        subtitle = next_line
        break

    return title, subtitle


def _looks_like_noise_line(line: str) -> bool:
    compact = line.strip()

    if not compact:
        return True

    if re.fullmatch(r"[\d\s/.-]+", compact):
        return True

    low = compact.lower()
    noise_markers = (
        "страница",
        "page",
        "лист",
        "каталог",
        "www.",
        "http://",
        "https://",
    )
    return any(marker in low for marker in noise_markers)


def _looks_like_table_row_text(line: str) -> bool:
    """
    Heuristic: line is likely part of table content, not title/subtitle.
    """
    if "  " in line or "\t" in line:
        return True

    digits = sum(ch.isdigit() for ch in line)
    letters = sum(ch.isalpha() for ch in line)

    if digits >= 4 and letters >= 1:
        return True

    if re.search(r"\b\d+[.,]?\d*\b", line) and re.search(
        r"\b(шт|мм|см|м|bar|pn|dn)\b", line, re.IGNORECASE
    ):
        return True

    return False


def _normalize_table_row(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize table row values and map common column names."""
    result: dict[str, Any] = {}

    field_mapping = {
        "sku": ["sku", "артикул", "код", "code", "型号", "модель", "model"],
        "size": ["size", "размер", "диаметр", "diameter", "dn"],
        "nominal_pressure": [
            "номинал_давление",
            "nominal_pressure",
            "pn",
            "pressure_class",
        ],
        "working_pressure_bar": [
            "раб_давление_бар",
            "working_pressure_bar",
            "давление",
            "pressure",
        ],
        "working_temperature_c": [
            "раб_температура_c",
            "working_temperature_c",
            "температура",
            "temp",
        ],
        "package_m": ["упак_м", "package_m", "бухта", "coil", "длина", "length"],
    }

    for key, value in row.items():
        clean_key = str(key).lower().strip()
        clean_value = clean_cell_value(value)

        mapped = False
        for standard, variants in field_mapping.items():
            if any(variant in clean_key for variant in variants):
                if standard == "sku":
                    clean_value = (
                        normalize_sku(clean_value) if clean_value else clean_value
                    )
                result[standard] = clean_value
                mapped = True
                break

        if not mapped:
            result[clean_key] = clean_value

    # fallback: if sku field not mapped directly, try detect in raw columns
    if not result.get("sku"):
        for key, value in result.items():
            if key.startswith("col_") and value:
                maybe_sku = normalize_sku(str(value))
                if _looks_like_sku(maybe_sku):
                    result["sku"] = maybe_sku
                    break

    return result


def _row_has_sku(row: dict[str, Any]) -> bool:
    sku = row.get("sku") or row.get("артикул")
    if not sku:
        return False
    return _looks_like_sku(str(sku))


def _looks_like_sku(value: str) -> bool:
    if not value:
        return False

    value = value.strip()
    if len(value) < 2:
        return False

    if not re.search(r"[A-Za-zА-Яа-я0-9]", value):
        return False

    # SKU usually has digits or alnum mix
    has_digit = any(ch.isdigit() for ch in value)
    has_alpha = any(ch.isalpha() for ch in value)
    return has_digit or (has_alpha and len(value) >= 4)


def _is_catalog_overview_page(text: str) -> bool:
    """
    Detect visual overview/index pages near the beginning of the catalog.

    These pages show product pictures with SKU captions and point to detailed
    pages via "стр. N"; they should not create products because descriptions
    are intentionally absent or too generic.
    """
    normalized = normalize_text(text).lower()
    if not normalized:
        return False

    page_refs = len(re.findall(r"\bстр\.?\s*\d+\b", normalized))
    series_headers = len(re.findall(r"\bсерия\s+смесител", normalized))
    sku_count = len(_extract_catalog_skus(text))

    detail_markers = (
        "материал",
        "размер упаковки",
        "тип установки",
        "подводка",
        "цвет-",
        "картридж",
        "аэратор",
    )

    return (
        page_refs >= 2
        and series_headers >= 2
        and sku_count >= 12
        and not any(marker in normalized for marker in detail_markers)
    )


def _is_meaningful_row(row: dict[str, Any], non_empty_values: int) -> bool:
    if non_empty_values == 0:
        return False

    values = [str(v).strip() for v in row.values() if v not in ("", None)]
    if not values:
        return False

    joined = " ".join(values).strip()
    if not joined:
        return False

    if re.fullmatch(r"[\d\s/.-]+", joined):
        return False

    return True


def extract_catalog_grid_from_page(
    pdf_path: str | Path,
    page_number: int,
    brand_hint: Optional[str] = None,
    source_file: Optional[str] = None,
) -> Optional[ProductBlock]:
    """
    Extract product data from catalog grid pages like:

    G101 Серия смесителей (латунь) 35mm стр. 21
    G10101 G10101-13 G10101-33 ...

    Images are ignored.
    """
    text = extract_text_from_page(pdf_path, page_number)
    if not text:
        return None

    normalized_text = normalize_text(text)

    title = _extract_catalog_title(normalized_text, page_number)
    if not title:
        logger.warning("Page %s: no catalog title found", page_number)
        return None

    skus = _extract_catalog_skus(normalized_text)
    if not skus:
        logger.warning("Page %s: no catalog skus found", page_number)
        return None

    rows = [{"sku": sku} for sku in skus]

    logger.info(
        "Page %s: catalog grid extracted title='%s' rows=%s",
        page_number,
        title,
        len(rows),
    )

    return ProductBlock(
        title=title,
        subtitle="",
        brand=brand_hint,
        page_number=page_number,
        rows=rows,
        source_file=source_file or str(pdf_path),
    )


def _extract_catalog_title(text: str) -> str:
    """
    Example:
    G52 Серия смесителей (латунь) 25mm стр. 1
    """
    text = normalize_text(text)

    # убрать мусор в начале страницы
    text = re.sub(
        r"^КАТАЛОГ\s+СМЕСИТЕЛИ\s+",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()

    # берем все, что стоит С НАЧАЛА секции до "стр. N"
    match = re.match(
        r"^(.*?)\s+стр\.\s*\d+",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return ""

    title = match.group(1).strip()
    title = re.sub(r"\s+", " ", title).strip()
    return title


def _extract_catalog_skus(text: str) -> list[str]:
    """
    Extract SKU-like tokens from catalog text.

    Examples:
    G1052-80
    G13102-13B
    G10103-229
    """
    pattern = re.compile(
        r"\b[A-ZА-Я]\d{4,}(?:-\d{1,3}[A-ZА-Я]?)?\b",
        re.IGNORECASE,
    )
    matches = pattern.findall(text)

    result: list[str] = []
    seen: set[str] = set()

    for raw in matches:
        sku = raw.strip().upper()
        if not sku:
            continue
        if sku in seen:
            continue
        seen.add(sku)
        result.append(sku)

    return result


def extract_catalog_grids_from_page(
    pdf_path: str | Path,
    page_number: int,
    brand_hint: Optional[str] = None,
    source_file: Optional[str] = None,
) -> list[ProductBlock]:
    """
    Extract multiple catalog blocks from one page.

    Example page:
    - G52 Серия смесителей (латунь) 25mm стр. 1
      G1052-80 G1052-83 ...
    - G102-13 Серия смесителей (латунь) 35mm стр. 5
      G10102-13 G13102-13 ...
    """
    text = extract_text_from_page(pdf_path, page_number)
    if not text:
        return []

    text = normalize_text(text)

    if _is_catalog_overview_page(text):
        logger.info("Page %s: skipping catalog overview/index page", page_number)
        return []

    # убираем мусор в начале страницы
    text = re.sub(
        r"^КАТАЛОГ\s+СМЕСИТЕЛИ\s+",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()

    header_pattern = re.compile(
        r"[A-ZА-Я][A-ZА-Я0-9-]*\s+Серия\s+смесителей.*?\s+стр\.\s*\d+",
        flags=re.IGNORECASE,
    )

    matches = list(header_pattern.finditer(text))
    if not matches:
        return []

    results: list[ProductBlock] = []

    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section = text[start:end].strip()

        title = _extract_catalog_title(section)
        if not title:
            continue

        skus = _extract_catalog_skus(section)
        if not skus:
            continue

        rows = [{"sku": sku} for sku in skus]

        results.append(
            ProductBlock(
                title=title,
                subtitle="",
                brand=brand_hint,
                page_number=page_number,
                rows=rows,
                source_file=source_file or str(pdf_path),
            )
        )

    return results


def _split_catalog_sections(text: str) -> list[str]:
    """
    Split one OCR/text blob into catalog sections by title markers.

    Marker example:
    G52 Серия смесителей (латунь) 25mm стр. 1
    """
    pattern = re.compile(
        r"(?=([A-ZА-Я0-9-]+\s+Серия\s+смесителей.*?стр\.\s*\d+))",
        flags=re.IGNORECASE,
    )

    matches = list(pattern.finditer(text))
    if not matches:
        return [text]

    sections: list[str] = []

    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = text[start:end].strip()
        if chunk:
            sections.append(chunk)

    return sections
