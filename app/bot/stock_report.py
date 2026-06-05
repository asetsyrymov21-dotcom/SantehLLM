from __future__ import annotations


def format_stock_import_report(data: dict) -> str:
    rows = data.get("rows_scanned", 0)
    updated = data.get("updated", 0)
    unchanged = data.get("unchanged", 0)
    no_product = data.get("skipped_no_product", 0)
    bad_brand = data.get("skipped_unsupported_brand", 0)
    bad_sku = data.get("skipped_invalid_sku", 0)
    bad_qty = data.get("skipped_invalid_qty", 0)
    duplicates = data.get("skipped_duplicate", 0)
    zero_qty = data.get("empty_qty_treated_as_zero", 0)
    errors = data.get("errors", 0)

    lines = [
        "✅ <b>Импорт завершён!</b>\n",
        f"📊 Строк в файле:       <b>{rows}</b>",
        f"✅ Обновлено:           <b>{updated}</b>",
        f"➖ Без изменений:       <b>{unchanged}</b>",
    ]

    if no_product:
        lines.append(f"❓ Не найдено в БД:     <b>{no_product}</b>")
    if bad_brand:
        lines.append(f"🚫 Неподдерж. бренд:   <b>{bad_brand}</b>")
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

    return "\n".join(lines)
