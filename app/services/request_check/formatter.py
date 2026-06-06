from __future__ import annotations

import html
from dataclasses import dataclass

from app.services.request_check.schemas import CheckedLine

_STATUS_EMOJI = {
    "Хватает": "✅",
    "Недостаточно": "⚠️",
    "Нет в наличии": "❌",
    "Не найден": "🔍",
}


@dataclass
class SummaryStats:
    total: int = 0
    enough: int = 0
    insufficient: int = 0
    out_of_stock: int = 0
    not_found: int = 0


def calc_summary(rows: list[CheckedLine]) -> SummaryStats:
    s = SummaryStats(total=len(rows))
    for row in rows:
        if row.status == "Хватает":
            s.enough += 1
        elif row.status == "Недостаточно":
            s.insufficient += 1
        elif row.status == "Нет в наличии":
            s.out_of_stock += 1
        elif row.status == "Не найден":
            s.not_found += 1
    return s


def format_summary(s: SummaryStats) -> str:
    return (
        f"📊 <b>Итого позиций: {s.total}</b>\n"
        f"✅ Хватает: {s.enough}\n"
        f"⚠️ Недостаточно: {s.insufficient}\n"
        f"❌ Нет в наличии: {s.out_of_stock}\n"
        f"🔍 Не найдено: {s.not_found}"
    )


def format_checked_lines_for_chat(rows: list[CheckedLine]) -> str:
    lines = []
    for row in rows:
        emoji = _STATUS_EMOJI.get(row.status, "❓")
        sku_display = row.sku or row.input_sku or "—"
        sku_text = html.escape(str(sku_display))
        status_text = html.escape(row.status)
        brand = html.escape(row.brand or "—")

        if row.found:
            name = html.escape(row.name or "без названия")
            product_line = f"{sku_text} ({name}) | {brand}"
        else:
            product_line = "Не найдено в каталоге"

        lines.append(
            f"{emoji} <b>{sku_text}</b> — {status_text}\n"
            f"   {product_line}\n"
            f"   Запрошено: {row.requested_qty} | Остаток: {row.stock_qty}"
        )

    summary = format_summary(calc_summary(rows))
    return "\n\n".join(lines) + f"\n\n{summary}"
