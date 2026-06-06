from __future__ import annotations

import html


def _format_breakdown(items: dict) -> str:
    if not items:
        return ""
    return ", ".join(f"{key}={value}" for key, value in items.items())


def _sheet_status_label(status: str) -> str:
    return {
        "valid_stock": "остатки",
        "article_only": "только артикул",
        "not_detected": "не распознан",
    }.get(status, status or "не распознан")


def format_stock_import_report(data: dict) -> str:
    filename = data.get("filename")
    selected_sheet = data.get("selected_sheet")
    sheets_checked = data.get("sheets_checked", 0)
    sheet_stats = data.get("sheet_stats") or []
    rows = data.get("rows_scanned", 0)
    updated = data.get("updated", 0)
    unchanged = data.get("unchanged", 0)
    sku_found = data.get("sku_found", updated + unchanged)
    no_product = data.get("skipped_no_product", 0)
    bad_brand = data.get("skipped_unsupported_brand", 0)
    bad_brand_breakdown = data.get("unsupported_brand_breakdown") or {}
    bad_sku = data.get("skipped_invalid_sku", 0)
    bad_qty = data.get("skipped_invalid_qty", 0)
    duplicates = data.get("skipped_duplicate", 0)
    zero_qty = data.get("empty_qty_treated_as_zero", 0)
    first_unmatched = data.get("first_unmatched_skus") or []
    first_duplicates = data.get("first_duplicate_skus") or []
    errors = data.get("errors", 0)

    lines = [
        "✅ <b>Импорт завершён!</b>\n",
    ]

    if filename:
        lines.append(f"📄 Файл: <b>{html.escape(str(filename))}</b>")
    if selected_sheet:
        lines.append(f"📑 Выбран лист: <b>{html.escape(str(selected_sheet))}</b>")
    if sheets_checked:
        lines.append(f"📚 Листов проверено: <b>{sheets_checked}</b>")

    lines.extend(
        [
            f"📊 Строк найдено:       <b>{rows}</b>",
            f"🔎 SKU найдено в БД:    <b>{sku_found}</b>",
        ]
    )

    if no_product:
        lines.append(f"❓ SKU не найдено:      <b>{no_product}</b>")

    lines.extend(
        [
            f"✅ Обновлено:           <b>{updated}</b>",
            f"➖ Без изменений:       <b>{unchanged}</b>",
        ]
    )

    if bad_brand:
        brand_detail = _format_breakdown(bad_brand_breakdown)
        suffix = f" ({brand_detail})" if brand_detail else ""
        lines.append(f"🚫 Неподдерж. бренд:   <b>{bad_brand}</b>{suffix}")
    if duplicates:
        lines.append(f"⚠️ Дубликаты (пропущ.): <b>{duplicates}</b>")
    if bad_sku:
        lines.append(f"⚠️ Пустой/неверный SKU: <b>{bad_sku}</b>")
    if bad_qty:
        lines.append(f"⚠️ Неверное кол-во:    <b>{bad_qty}</b>")
    if zero_qty:
        lines.append(f"ℹ️ Нет в наличии (пустое кол-во): <b>{zero_qty}</b>")
    if errors:
        lines.append(f"❌ Ошибок:             <b>{errors}</b>")

    if sheet_stats:
        lines.append("\n<b>Листы:</b>")
        for stat in sheet_stats[:10]:
            sheet = html.escape(str(stat.get("sheet", "")))
            status = _sheet_status_label(str(stat.get("status", "")))
            rows_found = stat.get("rows_found", 0)
            header_row = stat.get("header_row")
            header_text = f", заголовок {header_row}" if header_row is not None else ""
            lines.append(f"• {sheet}: {status}, строк {rows_found}{header_text}")
        if len(sheet_stats) > 10:
            lines.append(f"• ... ещё {len(sheet_stats) - 10}")

    if first_unmatched:
        lines.append("\n<b>Первые не найденные SKU:</b>")
        lines.append(", ".join(html.escape(str(sku)) for sku in first_unmatched[:20]))

    if first_duplicates:
        lines.append("\n<b>Первые дубликаты:</b>")
        lines.append(", ".join(html.escape(str(sku)) for sku in first_duplicates[:20]))

    return "\n".join(lines)
