from __future__ import annotations

import csv
import io
from typing import Any

from app.services.stock_import.excel_parser import (
    ExcelParseResult,
    ExcelStockRow,
    find_column_mapping,
)


def _decode_text(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16", "cp1251"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _detect_dialect(sample: str) -> csv.Dialect:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        return csv.excel


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {str(k).strip(): v for k, v in row.items() if str(k).strip()}


def parse_stock_text_file(content: bytes, filename: str) -> ExcelParseResult:
    text = _decode_text(content)
    non_empty_lines = [line for line in text.splitlines() if line.strip()]
    if not non_empty_lines:
        raise ValueError("Text stock file is empty")

    sample = "\n".join(non_empty_lines[:20])
    dialect = _detect_dialect(sample)
    reader = csv.reader(io.StringIO(text), dialect)
    rows = [row for row in reader if any(str(cell).strip() for cell in row)]

    if not rows:
        raise ValueError("No stock rows found in text file")

    headers = [str(cell).strip() for cell in rows[0]]
    data_rows = rows[1:]

    try:
        column_mapping = find_column_mapping(headers)
        article_col = column_mapping["article"]
        quantity_col = column_mapping.get("quantity")
        parsed_rows = []
        for idx, row in enumerate(data_rows, start=2):
            row_dict = _normalize_row(dict(zip(headers, row)))
            parsed_rows.append(
                ExcelStockRow(
                    raw_article=row_dict.get(article_col),
                    raw_quantity=row_dict.get(quantity_col) if quantity_col else None,
                    row_index=idx,
                    source_file=filename,
                    raw_data=row_dict,
                )
            )
    except ValueError:
        if len(headers) < 2:
            raise

        column_mapping = {"article": "article", "quantity": "quantity"}
        parsed_rows = []
        for idx, row in enumerate(rows, start=1):
            if len(row) < 2:
                continue
            parsed_rows.append(
                ExcelStockRow(
                    raw_article=row[0],
                    raw_quantity=row[1],
                    row_index=idx,
                    source_file=filename,
                    raw_data={"article": row[0], "quantity": row[1]},
                )
            )

    return ExcelParseResult(
        rows=parsed_rows,
        total_rows_scanned=len(rows),
        non_empty_rows=len(parsed_rows),
        column_mapping=column_mapping,
        sheet_name="text",
        file_path=filename,
    )
