from __future__ import annotations

import time
from io import BytesIO

from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from app.bot.api_client import APIClient
from app.bot.keyboards import sale_actions_keyboard, sale_confirm_keyboard
from app.bot.states import SaleStates

router = Router()


@router.callback_query(F.data.startswith("sell:"))
async def start_sale(call: types.CallbackQuery, state: FSMContext):
    product_id = int(call.data.split(":", 1)[1])
    await state.update_data(product_id=product_id)
    await state.set_state(SaleStates.waiting_quantity)
    await call.message.answer("Введите количество:")
    await call.answer()


@router.message(StateFilter(SaleStates.waiting_quantity))
async def receive_qty(message: types.Message, state: FSMContext):
    try:
        qty = float(message.text.replace(",", "."))
        if qty <= 0:
            raise ValueError
    except Exception:
        await message.answer("Введите положительное число для количества")
        return

    data = await state.get_data()
    product_id = data.get("product_id")
    api = APIClient()
    try:
        product = await api.get_product(product_id)
        inventory = await api.get_inventory(product_id)
        price = product.get("price") or 0
        currency = product.get("currency") or "USD"
        line_total = round(price * qty, 2)
        sale_number = f"TG-{int(time.time())}"
        payload = {
            "sale_number": sale_number,
            "sale_date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source_type": "telegram_text",
            "status": "draft",
            "customer_name": None,
            "currency": currency,
            "items": [
                {
                    "product_id": product_id,
                    "product_name_snapshot": product["name"],
                    "sku_snapshot": product.get("sku"),
                    "quantity": qty,
                    "unit": product.get("unit"),
                    "unit_price": price,
                    "line_total": line_total,
                }
            ],
        }
        sale = await api.create_sale(payload)
    except Exception as exc:
        await message.answer(f"Ошибка создания продажи: {exc}")
        await api.close()
        await state.clear()
        return
    await api.close()

    stock_str = "нет данных"
    stock_after = "-"
    if inventory:
        stock_val = inventory.get("stock_doc", 0)
        stock_str = f"{stock_val} {product.get('unit') or ''}".strip()
        stock_after = f"{max(stock_val - qty, 0)} {product.get('unit') or ''}".strip()

    await state.update_data(
        sale_id=sale["id"],
        sale_number=sale["sale_number"],
        product_name=product.get("name"),
        sku=product.get("sku"),
        qty=qty,
        price=price,
        line_total=line_total,
        currency=currency,
    )
    await state.set_state(SaleStates.waiting_confirmation)

    text = (
        "Проверьте продажу:\n\n"
        f"Товар: {product.get('name')}\n"
        f"SKU: {product.get('sku') or '-'}\n"
        f"Остаток: {stock_str}\n"
        f"Остаток после продажи: {stock_after}\n"
        f"Количество: {qty}\n"
        f"Цена: {price} {currency}\n"
        f"Сумма: {line_total} {currency}\n"
        f"Продажа: {sale['sale_number']}\n"
        f"Статус: draft"
    )
    await message.answer(text, reply_markup=sale_confirm_keyboard(sale["id"]))


@router.callback_query(F.data.startswith("sale_confirm:"))
async def confirm_sale_cb(call: types.CallbackQuery, state: FSMContext):
    sale_id = int(call.data.split(":", 1)[1])
    api = APIClient()
    try:
        sale = await api.confirm_sale(sale_id)
    except Exception as exc:
        await call.message.answer(f"Не удалось подтвердить продажу: {exc}")
        await api.close()
        await state.clear()
        await call.answer()
        return
    await api.close()
    await call.message.answer(
        f"Продажа подтверждена. № {sale['sale_number']}. Итог: {sale['total_amount']} {sale['currency']} Статус: {sale['status']}",
        reply_markup=sale_actions_keyboard(sale_id),
    )
    await state.clear()
    await call.answer()


@router.callback_query(F.data.startswith("sale_cancel:"))
async def cancel_sale_cb(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    sale_number = data.get("sale_number")
    await call.message.answer(
        f"Продажа не подтверждена. Черновик: {sale_number or 'n/a'}"
    )
    await state.clear()
    await call.answer()


@router.callback_query(F.data.startswith("inv:"))
async def send_invoice(call: types.CallbackQuery):
    sale_id = int(call.data.split(":", 1)[1])
    api = APIClient()
    try:
        doc = await api.create_invoice(sale_id)
        doc_id = doc.get("id")
        if not doc_id:
            raise RuntimeError("document id missing")
        content, filename = await api.download_document(doc_id)
        await call.message.answer_document(
            types.BufferedInputFile(content, filename=filename)
        )
    except Exception as exc:
        await call.message.answer(f"Не удалось получить накладную: {exc}")
    finally:
        await api.close()
    await call.answer()
