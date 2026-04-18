"""
PDF catalog parser for extracting product tables.
Supports multi-page tables and common catalog formats.
"""

from __future__ import annotations

import logging
import re
from io import BytesIO
from typing import List, Dict, Any, Optional

try:
    import pdfplumber

    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False

logger = logging.getLogger(__name__)


BAD_NAME_PATTERNS = [
    r"\bстр\.\s*\d+\b",
    r"\bpage\s+\d+\b",
    r"\bкаталог\b",
    r"\bновинки\b",
    r"\bwww\.",
    r"\bhttp\b",
]


def _looks_like_valid_product_name(name: str) -> bool:
    if not name:
        return False

    text = re.sub(r"\s+", " ", name).strip()
    text_lower = text.lower()

    if len(text) < 3 or len(text) > 120:
        return False

    for pattern in BAD_NAME_PATTERNS:
        if re.search(pattern, text_lower, flags=re.IGNORECASE):
            return False

    # слишком много SKU внутри name => blob/каталожный текст
    sku_hits = re.findall(
        r"\b[A-Z]{1,3}\d{2,5}(?:-\d{1,3}[A-Z0-9]?)?\b", text, flags=re.IGNORECASE
    )
    if len(sku_hits) >= 3:
        return False

    # слишком много цифр/мусора
    if len(re.findall(r"\d", text)) > 20:
        return False

    return True


def extract_tables_from_pdf(content: bytes) -> List[Dict[str, Any]]:
    """
    Extract product tables from PDF bytes.
    Returns list of rows as dictionaries.
    """
    if not PDFPLUMBER_AVAILABLE:
        raise ImportError("pdfplumber not installed. Run: pip install pdfplumber")

    products = []

    with pdfplumber.open(BytesIO(content)) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            logger.info(f"Processing page {page_num}")

            # Try to extract tables
            tables = page.extract_tables()

            if not tables:
                # No tables found, try to extract text and parse
                text = page.extract_text()
                if text:
                    parsed = _parse_text_to_products(text, page_num)
                    products.extend(parsed)
                continue

            # Process each table
            for table in tables:
                if not table or len(table) < 2:
                    continue

                # Detect headers
                headers = _detect_headers(table[0])

                for row in table[1:]:
                    product = _row_to_product(row, headers, page_num)
                    if product and product.get("sku") and product.get("name"):
                        products.append(product)

    logger.info(f"Extracted {len(products)} products from PDF")
    return products


def _detect_headers(header_row: List[str]) -> Dict[str, int]:
    """Map column names to indices based on common patterns."""
    headers = {}

    for idx, cell in enumerate(header_row):
        if not cell:
            continue
        cell_lower = str(cell).lower().strip()

        # SKU / Артикул / Код
        if any(
            kw in cell_lower for kw in ["sku", "артикул", "код", "code", "型号", "货号"]
        ):
            headers["sku"] = idx
        # Name / Название / Наименование
        elif any(
            kw in cell_lower
            for kw in [
                "name",
                "название",
                "наименование",
                "товар",
                "product",
                "名称",
                "品名",
            ]
        ):
            headers["name"] = idx
        # Brand / Бренд / Производитель
        elif any(
            kw in cell_lower
            for kw in ["brand", "бренд", "производитель", "марка", "品牌"]
        ):
            headers["brand"] = idx
        # Category / Категория
        elif any(
            kw in cell_lower
            for kw in ["category", "категория", "тип", "серия", "类别", "系列"]
        ):
            headers["category"] = idx
        # Price / Цена
        elif any(
            kw in cell_lower for kw in ["price", "цена", "стоимость", "价格", "单价"]
        ):
            headers["price"] = idx
        # Description / Описание
        elif any(kw in cell_lower for kw in ["description", "описание", "描述"]):
            headers["description"] = idx

    return headers


def _row_to_product(
    row: List[str], headers: Dict[str, int], page_num: int
) -> Optional[Dict[str, Any]]:
    """Convert table row to product dict."""
    product = {"page": page_num, "attributes_json": {}}

    # Map known columns
    if "sku" in headers:
        product["sku"] = _clean_sku(row[headers["sku"]])
    if "name" in headers:
        product["name"] = _clean_text(row[headers["name"]])
    if "brand" in headers:
        product["brand"] = _clean_text(row[headers["brand"]])
    if "category" in headers:
        product["category"] = _clean_text(row[headers["category"]])
    if "price" in headers:
        product["price"] = _parse_price(row[headers["price"]])
    if "description" in headers:
        product["description"] = _clean_text(row[headers["description"]])

    # Try to infer from column position if headers not detected
    if not product.get("sku") and len(row) > 0:
        product["sku"] = _clean_sku(row[0])
    if not product.get("name") and len(row) > 1:
        product["name"] = _clean_text(row[1])

    # Extract remaining columns as attributes
    for idx, cell in enumerate(row):
        if cell and idx not in headers.values():
            col_name = f"col_{idx}"
            product["attributes_json"][col_name] = str(cell).strip()

    return product if product.get("sku") and product.get("name") else None


def _parse_text_to_products(text: str, page_num: int) -> List[Dict[str, Any]]:
    """Fallback: parse unstructured text for product patterns."""
    products = []
    lines = text.split("\n")

    for line in lines:
        line = line.strip()
        if not line:
            continue

        match = re.match(
            r"^([A-Z]{1,3}\d{2,5}(?:-\d{1,3}[A-Z0-9]?)?)\s+(.+)$",
            line,
            flags=re.IGNORECASE,
        )
        if not match:
            continue

        sku = match.group(1).strip()
        name = re.sub(r"\s+", " ", match.group(2)).strip()

        if not _looks_like_valid_product_name(name):
            logger.warning(
                "Skipping suspicious fallback row",
                extra={"page": page_num, "sku": sku, "name": name[:200]},
            )
            continue

        products.append(
            {
                "sku": sku,
                "name": name,
                "page": page_num,
            }
        )

    return products


def _clean_sku(value: Any) -> Optional[str]:
    """Clean SKU value."""
    if not value:
        return None
    sku = str(value).strip()
    # Remove common prefixes/suffixes
    sku = re.sub(r"^(арт\.|артикул|код|code)[:\s]*", "", sku, flags=re.IGNORECASE)
    return sku if sku else None


def _clean_text(value: Any) -> Optional[str]:
    """Clean text value."""
    if not value:
        return None
    text = str(value).strip()
    # Remove excessive whitespace
    text = re.sub(r"\s+", " ", text)
    return text if text else None


def _parse_price(value: Any) -> Optional[float]:
    """Parse price from various formats."""
    if not value:
        return None

    # Remove currency symbols and whitespace
    price_str = str(value).strip()
    price_str = re.sub(r"[^\d.,]", "", price_str)

    # Handle different decimal separators
    if "," in price_str and "." in price_str:
        # 1.234,56 format
        price_str = price_str.replace(".", "").replace(",", ".")
    elif "," in price_str:
        # Might be decimal separator or thousands
        parts = price_str.split(",")
        if len(parts) == 2 and len(parts[1]) <= 2:
            price_str = price_str.replace(",", ".")
        else:
            price_str = price_str.replace(",", "")

    try:
        return float(price_str) if price_str else None
    except ValueError:
        return None
