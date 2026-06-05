"""Excel parser for stock import.

Reads Excel files and extracts stock data with proper structure detection.
Does NOT rely on max_row - works with actual data rows only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Iterator

logger = logging.getLogger(__name__)


# Default sheets to read for stock files.
# "总" is the combined stock sheet in current supplier files. If it is absent,
# fall back to legacy category-level sheets.
DEFAULT_FRAP_SHEETS = ["总"]
FALLBACK_FRAP_SHEETS = ["水", "接"]

# Aliases for matching Russian headers from stock files
STOCK_COLUMN_ALIASES: dict[str, list[str]] = {
    "article": [
        "артикул",
        "арт.",
        "арт",
        "sku",
        "код",
        "code",
        "модель",
        "model",
        "article",
        "artikel",
        "артикул товара",
        "код товара",
        # Chinese aliases
        "型号",
        "货号",
        "产品编号",
        "商品编码",
        "客户号",
    ],
    "quantity": [
        "количество",
        "остаток",
        "qty",
        "quantity",
        "stock",
        "наличие",
        "штук",
        "шт",
        "шт.",
        "остаток на складе",
        "остатки",
        "остаток склад",
        "кол-во",
        "колво",
        "остаток (шт)",
        "остаток, шт",
        # Chinese aliases
        "库存",
        "可用库存",
        "数量",
        "预计可发量(库存)",
    ],
    # Note: "1с" column is intentionally NOT used as authoritative source
    # It may contain formulas/VLOOKUP and is only for reference
}

QUANTITY_NEGATIVE_KEYWORDS = [
    "цена",
    "ррц",
    "опт",
    "скид",
    "price",
    "cost",
    "amount",
    "сумма",
    "стоимость",
]


def normalize_header_name(header: str) -> str:
    """Normalize column header for matching.

    - Strip whitespace
    - Convert to lowercase
    - Collapse multiple spaces
    - Remove extra punctuation
    """
    if not header:
        return ""

    import re

    normalized = str(header).strip().lower()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = normalized.strip(".:-")
    return normalized


def compact_header_name(header: str) -> str:
    """Normalize header for fuzzy matching without punctuation/spaces."""
    import re

    normalized = normalize_header_name(header)
    return re.sub(r"[^0-9a-zа-яё\u4e00-\u9fff]+", "", normalized)


def _has_negative_quantity_signal(normalized: str) -> bool:
    return any(keyword in normalized for keyword in QUANTITY_NEGATIVE_KEYWORDS)


def _matches_article_header(normalized: str, compact: str) -> bool:
    article_aliases = STOCK_COLUMN_ALIASES["article"]
    article_aliases_normalized = {normalize_header_name(alias) for alias in article_aliases}
    article_aliases_compact = {compact_header_name(alias) for alias in article_aliases}

    if normalized in article_aliases_normalized or compact in article_aliases_compact:
        return True

    contains_signals = [
        "артикул",
        "sku",
        "код товара",
        "модель",
        "article",
        "artikel",
        "model",
        "型号",
        "货号",
        "产品编号",
        "商品编码",
        "客户号",
    ]
    return any(signal in normalized for signal in contains_signals)


def _matches_quantity_header(normalized: str, compact: str) -> bool:
    if _has_negative_quantity_signal(normalized):
        return False

    quantity_aliases = STOCK_COLUMN_ALIASES["quantity"]
    quantity_aliases_normalized = {normalize_header_name(alias) for alias in quantity_aliases}
    quantity_aliases_compact = {compact_header_name(alias) for alias in quantity_aliases}

    if normalized in quantity_aliases_normalized or compact in quantity_aliases_compact:
        return True

    contains_signals = [
        "остат",
        "налич",
        "количество",
        "кол во",
        "кол-во",
        "колво",
        "склад",
        "qty",
        "quantity",
        "stock",
        "inventory",
        "available",
        "库存",
        "数量",
    ]

    if any(signal in normalized for signal in contains_signals):
        return True

    return "шт" in normalized and not _has_negative_quantity_signal(normalized)


def detect_stock_header_field(header: str) -> str | None:
    """Detect the stock-import field represented by a source column header."""
    normalized = normalize_header_name(header)
    compact = compact_header_name(header)

    if not normalized:
        return None

    if _matches_article_header(normalized, compact):
        return "article"

    if _matches_quantity_header(normalized, compact):
        return "quantity"

    return None


def find_column_mapping(headers: list[str]) -> dict[str, str]:
    """Map Excel headers to standard field names.

    Args:
        headers: List of column headers from Excel

    Returns:
        Mapping of standard_field -> original_excel_header

    Raises:
        ValueError: If required columns (article) not found
    """
    mapping: dict[str, str] = {}

    for header in headers:
        field_name = detect_stock_header_field(header)
        if field_name and field_name not in mapping:
            mapping[field_name] = header
            logger.debug(f"Mapped '{header}' -> '{field_name}'")

    # Check for required fields
    if "article" not in mapping:
        logger.error("Excel headers raw: %s", headers)
        logger.error(
            "Excel headers normalized: %s", [normalize_header_name(h) for h in headers]
        )
        available = ", ".join(f"'{h}'" for h in headers[:20])
        raise ValueError(
            f"Required column 'article' not found in Excel. "
            f"Available columns (first 20): {available}"
        )

    logger.info(
        f"Column mapping found: article='{mapping['article']}', "
        f"quantity='{mapping.get('quantity', 'NOT FOUND')}'"
    )

    return mapping


@dataclass
class ExcelStockRow:
    """Represents a single stock row from Excel."""

    raw_article: Optional[str]
    raw_quantity: Any
    row_index: int  # 1-based for human readability
    source_file: str
    sheet_name: Optional[str] = None  # Source sheet name

    # Original row data for debugging
    raw_data: dict[str, Any] = field(repr=False, default_factory=dict)


@dataclass
class ExcelParseResult:
    """Result of parsing Excel file."""

    rows: list[ExcelStockRow]
    total_rows_scanned: int
    non_empty_rows: int
    column_mapping: dict[str, str]
    sheet_name: str
    file_path: str


def is_empty_row(row_data: dict[str, Any], column_mapping: dict[str, str]) -> bool:
    """Check if row is effectively empty (no article, no quantity)."""
    article_col = column_mapping.get("article")
    quantity_col = column_mapping.get("quantity")

    has_article = False
    has_quantity = False

    if article_col and row_data.get(article_col):
        val = str(row_data[article_col]).strip()
        if val and val.lower() not in ("none", "nan", "null", ""):
            has_article = True

    if quantity_col and row_data.get(quantity_col):
        val = row_data[quantity_col]
        if val is not None and str(val).strip():
            has_quantity = True

    return not (has_article or has_quantity)


class StockExcelParser:
    """Parser for stock Excel files with smart row detection."""

    def __init__(self, file_path: str | Path, header_row: int = 0):
        """
        Args:
            file_path: Path to Excel file
            header_row: 0-based index of header row (default: 0)
        """
        self.file_path = Path(file_path)
        self.header_row = header_row
        self._column_mapping: Optional[dict[str, str]] = None

    def parse(
        self,
        sheet_name: Optional[int | str | list[str]] = None,
        use_default_sheets: bool = True,
    ) -> ExcelParseResult:
        """Parse Excel file and return structured rows.

        Uses pandas for reading but with custom empty row detection.
        Stops at streak of empty rows to avoid reading formula-filled empty cells.

        Args:
            sheet_name: Sheet(s) to read. Can be:
                - None: use default sheets if use_default_sheets=True, else first sheet
                - str: single sheet name
                - list[str]: multiple sheet names
            use_default_sheets: If True and sheet_name is None, use DEFAULT_FRAP_SHEETS

        Returns:
            ExcelParseResult with parsed rows and metadata
        """
        import pandas as pd

        # Determine which sheets to read
        sheets_to_read: Optional[int | str | list[str]]
        if sheet_name is not None:
            sheets_to_read = sheet_name
            if isinstance(sheet_name, int):
                sheet_desc = f"sheet index {sheet_name}"
            elif isinstance(sheet_name, str):
                sheet_desc = sheet_name
            else:
                sheet_desc = f"{len(sheet_name)} sheets"
        elif use_default_sheets:
            import pandas as pd

            available_sheets = set(
                pd.ExcelFile(self.file_path, engine="openpyxl").sheet_names
            )
            sheets_to_read = [
                sheet for sheet in DEFAULT_FRAP_SHEETS if sheet in available_sheets
            ]
            if not sheets_to_read:
                sheets_to_read = [
                    sheet for sheet in FALLBACK_FRAP_SHEETS if sheet in available_sheets
                ]
            if not sheets_to_read:
                sheets_to_read = 0
                sheet_desc = "first sheet"
            else:
                sheet_desc = f"default sheets {sheets_to_read}"
        else:
            sheets_to_read = 0  # First sheet only
            sheet_desc = "first sheet"

        logger.info(f"Reading Excel: {self.file_path}, sheet={sheet_desc}")

        # Read with pandas - may return dict if multiple sheets
        read_result = pd.read_excel(
            self.file_path,
            sheet_name=sheets_to_read,
            header=self.header_row,
            engine="openpyxl",
            dtype=str,  # Read everything as string to preserve leading zeros
        )

        # Handle multi-sheet result (dict) vs single sheet (DataFrame)
        if isinstance(read_result, dict):
            parsed_rows: list[ExcelStockRow] = []
            total_rows_scanned = 0
            first_mapping: dict[str, str] | None = None
            parsed_sheet_names: list[str] = []

            for actual_sheet, df in read_result.items():
                sheet_rows, scanned, mapping = self._parse_dataframe(
                    df=df,
                    actual_sheet=str(actual_sheet),
                    sheet_name=str(actual_sheet),
                )
                parsed_rows.extend(sheet_rows)
                total_rows_scanned += scanned
                parsed_sheet_names.append(str(actual_sheet))
                if first_mapping is None:
                    first_mapping = mapping

            return ExcelParseResult(
                rows=parsed_rows,
                total_rows_scanned=total_rows_scanned,
                non_empty_rows=len(parsed_rows),
                column_mapping=first_mapping or {},
                sheet_name=f"multiple: {parsed_sheet_names}",
                file_path=str(self.file_path),
            )
        else:
            # Single sheet
            df = read_result
            actual_sheet = sheet_name if isinstance(sheet_name, str) else "first"

        parsed_rows, total_rows_scanned, mapping = self._parse_dataframe(
            df=df,
            actual_sheet=str(actual_sheet),
            sheet_name=sheet_name if isinstance(sheet_name, str) else None,
        )

        return ExcelParseResult(
            rows=parsed_rows,
            total_rows_scanned=total_rows_scanned,
            non_empty_rows=len(parsed_rows),
            column_mapping=mapping,
            sheet_name=str(actual_sheet),
            file_path=str(self.file_path),
        )

    def _parse_dataframe(
        self,
        df: Any,
        actual_sheet: str,
        sheet_name: str | None,
    ) -> tuple[list[ExcelStockRow], int, dict[str, str]]:
        """Parse one pandas DataFrame using its own column mapping."""
        import pandas as pd

        # Convert NaN to None for cleaner handling
        df = df.where(pd.notnull(df), None)

        # Get headers and build mapping
        headers = list(df.columns)
        logger.info(f"Found {len(headers)} columns in Excel")

        try:
            column_mapping = find_column_mapping(headers)
        except Exception:
            logger.exception(
                "Failed to build stock column mapping: file=%s, sheet=%s, headers=%s",
                self.file_path,
                actual_sheet,
                headers,
            )

            # Fallback: sheet without header row.
            # Example: pandas used first data row as headers like ['F001', '15'].
            if len(headers) == 2:
                logger.warning(
                    "Detected 2-column sheet without recognizable headers. "
                    "Using direct SKU/quantity mode: file=%s sheet=%s headers=%s",
                    self.file_path,
                    actual_sheet,
                    headers,
                )

                original_headers = headers

                # Current headers are actually first data row, so restore them as first record
                df.columns = ["article", "quantity"]
                first_row = {
                    "article": original_headers[0],
                    "quantity": original_headers[1],
                }
                df = pd.concat([pd.DataFrame([first_row]), df], ignore_index=True)

                self._column_mapping = {
                    "article": "article",
                    "quantity": "quantity",
                }
                column_mapping = self._column_mapping

                logger.info(
                    "Applied direct SKU/quantity mode: article='article', quantity='quantity'"
                )
            else:
                raise
        else:
            self._column_mapping = column_mapping

        # Convert to list of dicts
        all_rows = df.to_dict(orient="records")

        # Process rows with empty row detection
        parsed_rows: list[ExcelStockRow] = []
        empty_streak = 0
        MAX_EMPTY_STREAK = 50  # Stop after 50 consecutive empty rows

        for idx, row_data in enumerate(all_rows, start=1):  # 1-based for display
            # Check for empty row
            if is_empty_row(row_data, column_mapping):
                empty_streak += 1
                if empty_streak >= MAX_EMPTY_STREAK:
                    logger.info(
                        f"Stopped at row {idx} after {MAX_EMPTY_STREAK} empty rows"
                    )
                    break
                continue

            empty_streak = 0  # Reset on non-empty row

            article_col = column_mapping.get("article")
            quantity_col = column_mapping.get("quantity")

            # Extract sheet name from row data (set by _concat_sheets for multi-sheet)
            # or use the passed sheet_name for single sheet
            row_sheet_name = row_data.get("__sheet_name")
            if not row_sheet_name and isinstance(sheet_name, str):
                row_sheet_name = sheet_name

            parsed_rows.append(
                ExcelStockRow(
                    raw_article=row_data.get(article_col),
                    raw_quantity=row_data.get(quantity_col) if quantity_col else None,
                    row_index=idx + self.header_row + 1,  # Adjust for header + 1-based
                    source_file=str(self.file_path),
                    sheet_name=row_sheet_name,
                    raw_data=dict(row_data),  # Copy for debugging
                )
            )

        return parsed_rows, len(all_rows), column_mapping

    def _concat_sheets(self, sheets_dict: dict[str, Any]) -> Any:
        """Concatenate multiple sheets into single DataFrame.

        Args:
            sheets_dict: Dict mapping sheet_name -> DataFrame

        Returns:
            Concatenated DataFrame with __sheet_name column
        """
        import pandas as pd

        processed_sheets = []

        for sheet_name, df in sheets_dict.items():
            if df is None or df.empty:
                logger.warning(f"Sheet '{sheet_name}' is empty, skipping")
                continue

            # Drop completely empty rows
            df = df.dropna(how="all")

            if df.empty:
                logger.warning(
                    f"Sheet '{sheet_name}' has no data after dropna, skipping"
                )
                continue

            # Add sheet name column for tracing
            df = df.copy()
            df["__sheet_name"] = sheet_name
            processed_sheets.append(df)
            logger.info(f"Sheet '{sheet_name}': {len(df)} rows")

        if not processed_sheets:
            raise ValueError("No valid data found in any sheet")

        # Concatenate all sheets
        result = pd.concat(processed_sheets, ignore_index=True)
        logger.info(
            f"Concatenated {len(processed_sheets)} sheets, total {len(result)} rows"
        )
        return result

    def iter_rows(self, sheet_name: Optional[str] = None) -> Iterator[ExcelStockRow]:
        """Parse and yield rows one by one (generator version)."""
        result = self.parse(sheet_name)
        yield from result.rows
