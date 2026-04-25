"""Excel file loading utilities.

Handles reading Excel files and yielding raw row data.
"""

from typing import Iterator, Any
from pathlib import Path

import openpyxl
from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet

EMPTY_ROW_BREAK_STREAK = 50


def _get_cell_value(cell) -> Any:
    """Extract value from cell, handling empty cells."""
    if cell.value is None:
        return None
    return cell.value


def _is_row_empty(row: tuple) -> bool:
    """Check if all cells in row are empty."""
    return all(cell.value is None for cell in row)


def _make_safe_header(header: str, index: int) -> str:
    """Create safe header name from cell value or index."""
    if header and str(header).strip():
        return str(header).strip()
    return f"column_{index}"


class ExcelLoader:
    """Loader for Excel product data files."""

    def __init__(self, file_path: str | Path):
        """Initialize loader with file path.

        Args:
            file_path: Path to Excel file
        """
        self.file_path = Path(file_path)

    def read_sheet_names(self) -> list[str]:
        """Get list of available sheet names.

        Returns:
            List of sheet names in the workbook
        """
        wb: Workbook = openpyxl.load_workbook(
            self.file_path, read_only=True, data_only=True
        )
        try:
            return wb.sheetnames
        finally:
            wb.close()

    def load_excel_rows(
        self,
        sheet_name: str | None = None,
        header_row: int = 0,
    ) -> list[dict[str, Any]]:
        """Load all rows from Excel as list of dicts.

        Args:
            sheet_name: Specific sheet to read, or None for default
            header_row: Row index containing column headers (0-based)

        Returns:
            List of row dictionaries
        """
        wb: Workbook = openpyxl.load_workbook(
            self.file_path, read_only=True, data_only=True
        )
        try:
            if sheet_name:
                ws: Worksheet = wb[sheet_name]
            else:
                ws = wb.active
                if ws is None:
                    ws = wb[wb.sheetnames[0]]

            headers: list[str] = []
            rows: list[dict[str, Any]] = []
            empty_streak = 0

            for idx, row in enumerate(ws.iter_rows(values_only=False)):
                if idx < header_row:
                    continue

                if idx == header_row:
                    if _is_row_empty(row):
                        continue

                    headers = [
                        _make_safe_header(str(cell.value) if cell.value else "", i)
                        for i, cell in enumerate(row)
                    ]
                    continue

                if _is_row_empty(row):
                    empty_streak += 1
                    if empty_streak >= EMPTY_ROW_BREAK_STREAK:
                        break
                    continue

                row_dict = {}
                for i, cell in enumerate(row):
                    if i < len(headers):
                        row_dict[headers[i]] = _get_cell_value(cell)

                if any(v is not None for v in row_dict.values()):
                    rows.append(row_dict)
                    empty_streak = 0
                else:
                    empty_streak += 1
                    if empty_streak >= EMPTY_ROW_BREAK_STREAK:
                        break

            return rows
        finally:
            wb.close()

    def iter_sheet_rows(
        self,
        sheet_name: str,
        header_row: int = 0,
        start_row: int | None = None,
        end_row: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Iterate rows from a sheet lazily.

        Args:
            sheet_name: Sheet to read
            header_row: Row index with headers (0-based)
            start_row: First data row (after header if None)
            end_row: Last row to read (all if None)

        Yields:
            Row dictionaries one at a time
        """
        wb: Workbook = openpyxl.load_workbook(
            self.file_path, read_only=True, data_only=True
        )
        try:
            ws: Worksheet = wb[sheet_name]

            headers: list[str] = []
            row_idx = 0
            empty_streak = 0

            for row in ws.iter_rows(values_only=False):
                if row_idx < header_row:
                    row_idx += 1
                    continue

                if row_idx == header_row:
                    if _is_row_empty(row):
                        row_idx += 1
                        continue

                    headers = [
                        _make_safe_header(str(cell.value) if cell.value else "", i)
                        for i, cell in enumerate(row)
                    ]
                    row_idx += 1
                    continue

                if start_row is not None and row_idx < start_row:
                    row_idx += 1
                    continue

                if end_row is not None and row_idx > end_row:
                    break

                if _is_row_empty(row):
                    empty_streak += 1
                    if empty_streak >= EMPTY_ROW_BREAK_STREAK:
                        break
                    row_idx += 1
                    continue

                row_dict = {}
                for i, cell in enumerate(row):
                    if i < len(headers):
                        row_dict[headers[i]] = _get_cell_value(cell)

                if any(v is not None for v in row_dict.values()):
                    yield row_dict
                    empty_streak = 0
                else:
                    empty_streak += 1
                    if empty_streak >= EMPTY_ROW_BREAK_STREAK:
                        break

                row_idx += 1
        finally:
            wb.close()
