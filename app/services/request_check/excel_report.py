from __future__ import annotations

import io
import datetime

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from app.services.request_check.schemas import CheckedLine
from app.services.request_check.formatter import calc_summary

_HEADERS = ["Input SKU", "SKU", "Название", "Бренд", "Запрошено", "Остаток", "Статус"]

_STATUS_FILLS = {
    "Хватает": PatternFill("solid", fgColor="C6EFCE"),
    "Недостаточно": PatternFill("solid", fgColor="FFEB9C"),
    "Нет в наличии": PatternFill("solid", fgColor="FFC7CE"),
    "Не найден": PatternFill("solid", fgColor="F2F2F2"),
}

_HEADER_FILL = PatternFill("solid", fgColor="4472C4")
_HEADER_FONT = Font(bold=True, color="FFFFFF")


def generate_excel_report(rows: list[CheckedLine]) -> io.BytesIO:
    wb = openpyxl.Workbook()

    _write_main_sheet(wb.active, rows)
    _write_summary_sheet(wb.create_sheet("Сводка"), rows)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def _write_main_sheet(ws, rows: list[CheckedLine]) -> None:
    ws.title = "Проверка заявки"

    for col_idx, header in enumerate(_HEADERS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.alignment = Alignment(horizontal="center")

    for row_idx, row in enumerate(rows, start=2):
        values = [
            row.input_sku,
            row.sku or "",
            row.name or "",
            row.brand or "",
            row.requested_qty,
            row.stock_qty,
            row.status,
        ]
        fill = _STATUS_FILLS.get(row.status)
        for col_idx, value in enumerate(values, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            if fill:
                cell.fill = fill

    _autofit(ws, len(_HEADERS))


def _write_summary_sheet(ws, rows: list[CheckedLine]) -> None:
    ws.title = "Сводка"
    s = calc_summary(rows)

    data = [
        ("Всего позиций", s.total),
        ("Хватает", s.enough),
        ("Недостаточно", s.insufficient),
        ("Нет в наличии", s.out_of_stock),
        ("Не найдено", s.not_found),
    ]

    for row_idx, (label, value) in enumerate(data, start=1):
        ws.cell(row=row_idx, column=1, value=label).font = Font(bold=True)
        ws.cell(row=row_idx, column=2, value=value)

    ws.column_dimensions["A"].width = 20
    ws.column_dimensions["B"].width = 10


def _autofit(ws, col_count: int) -> None:
    for col_idx in range(1, col_count + 1):
        max_len = 0
        col_letter = get_column_letter(col_idx)
        for row in ws.iter_rows(min_col=col_idx, max_col=col_idx):
            for cell in row:
                if cell.value:
                    max_len = max(max_len, len(str(cell.value)))
        ws.column_dimensions[col_letter].width = min(max_len + 4, 50)


def get_report_filename() -> str:
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"request_check_{ts}.xlsx"
