from aiogram import Dispatcher


def register_handlers(dp: Dispatcher) -> None:
    from app.bot.handlers import (
        start,
        assistant,
        assistant_admin,
        search,
        product,
        navigation,
        sale,
        voice,
        batch_sku,
        catalog_import,
        excel_request,
        stock_import,
    )

    dp.include_router(start.router)
    dp.include_router(assistant.router)
    dp.include_router(assistant_admin.router)
    dp.include_router(batch_sku.router)
    dp.include_router(catalog_import.router)
    dp.include_router(excel_request.router)
    dp.include_router(stock_import.router)
    dp.include_router(search.router)
    dp.include_router(product.router)
    dp.include_router(navigation.router)
    dp.include_router(sale.router)
    dp.include_router(voice.router)
