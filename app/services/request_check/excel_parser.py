from __future__ import annotations

import io
from typing import Optional

import openpyxl

from app.services.request_check.schemas import RequestLine

_SKU_ALIASES = {"sku", "артикул", "код", "товарный код"}
_QTY_ALIASES = {"qty", "quantity", "количество", "кол-во", "заказ", "нужно"}


def parse_excel_request(file_bytes: bytes) -> list[RequestLine]:
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    ws = wb.worksheets[0]

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []

    # пробуем найти заголовки в первой строке
    sku_col, qty_col = _find_columns(rows[0])

    # если заголовков нет — считаем что первая колонка это SKU, без qty
    if sku_col is None:
        data_rows = rows
        qty_col = None
        sku_col = 0
    else:
        data_rows = rows[1:]

    result = []
    for row in data_rows:
        if not row or all(v is None for v in row):
            continue

        raw_sku = _get_cell(row, sku_col)
        if not raw_sku:
            continue

        sku = str(raw_sku).upper().strip()
        if not sku:
            continue

        qty = 1
        if qty_col is not None:
            qty = _parse_qty(_get_cell(row, qty_col))

        result.append(RequestLine(raw=str(raw_sku), sku=sku, requested_qty=qty))

    wb.close()
    return result


def _find_columns(header_row) -> tuple[Optional[int], Optional[int]]:
    sku_col = None
    qty_col = None
    for idx, cell in enumerate(header_row):
        if cell is None:
            continue
        val = str(cell).lower().strip()
        if val in _SKU_ALIASES and sku_col is None:
            sku_col = idx
        if val in _QTY_ALIASES and qty_col is None:
            qty_col = idx
    return sku_col, qty_col


def _get_cell(row, idx: int):
    if idx < len(row):
        return row[idx]
    return None


def _parse_qty(value) -> int:
    if value is None:
        return 1
    try:
        qty = int(float(str(value)))
        return max(1, qty)
    except (ValueError, TypeError):
        return 1
