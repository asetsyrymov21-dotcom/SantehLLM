from __future__ import annotations

from app.services.request_check.schemas import RequestLine, CheckedLine


def _resolve_status(found: bool, stock_qty: int, requested_qty: int) -> str:
    if not found:
        return "Не найден"
    if stock_qty <= 0:
        return "Нет в наличии"
    if stock_qty >= requested_qty:
        return "Хватает"
    return "Недостаточно"


async def check_request_lines(
    api_client,
    request_lines: list[RequestLine],
) -> list[CheckedLine]:
    """
    Принимает APIClient и список RequestLine.
    Делает lookup по каждому SKU через API.
    Возвращает list[CheckedLine].
    """
    results: list[CheckedLine] = []

    for line in request_lines:
        checked = await _check_one(api_client, line)
        results.append(checked)

    return results


async def _check_one(api_client, line: RequestLine) -> CheckedLine:
    try:
        products = await api_client.search_products(line.sku)
    except Exception:
        return CheckedLine(
            input_sku=line.sku,
            requested_qty=line.requested_qty,
            found=False,
            status="Не найден",
        )

    # ищем точное совпадение по SKU
    product = None
    for p in products or []:
        if p.get("sku", "").upper() == line.sku.upper():
            product = p
            break

    if not product:
        return CheckedLine(
            input_sku=line.sku,
            requested_qty=line.requested_qty,
            found=False,
            status="Не найден",
        )

    product_id = product["id"]
    stock_qty = 0

    try:
        inv = await api_client.get_inventory(product_id)
        if inv:
            stock_qty = int(inv.get("stock_doc", 0) or 0)
    except Exception:
        pass

    status = _resolve_status(True, stock_qty, line.requested_qty)

    return CheckedLine(
        input_sku=line.sku,
        requested_qty=line.requested_qty,
        found=True,
        sku=product.get("sku"),
        name=product.get("name"),
        brand=product.get("brand"),
        stock_qty=stock_qty,
        status=status,
    )
