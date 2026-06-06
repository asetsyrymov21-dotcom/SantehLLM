from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder


MAIN_MENU_BUTTON = "🏠 Главное меню"
ASK_ASSISTANT_BUTTON = "💬 Спросить ассистента"
ASSISTANT_DRAFTS_BUTTON = "📝 Черновики ассистента"
SEARCH_PRODUCT_BUTTON = "🔎 Поиск товара"
CHECK_REQUEST_BUTTON = "📋 Проверить заявку"
CHECK_EXCEL_REQUEST_BUTTON = "📂 Проверить Excel-заявку"
LEGACY_CHECK_EXCEL_REQUEST_BUTTON = "📂 Загрузить Excel-заявку"
IMPORT_CATALOG_BUTTON = "🧾 Загрузить каталог"
IMPORT_STOCK_BUTTON = "📥 Загрузить остатки"

MAIN_MENU_BUTTONS = {
    MAIN_MENU_BUTTON,
    ASK_ASSISTANT_BUTTON,
    ASSISTANT_DRAFTS_BUTTON,
    SEARCH_PRODUCT_BUTTON,
    CHECK_REQUEST_BUTTON,
    CHECK_EXCEL_REQUEST_BUTTON,
    LEGACY_CHECK_EXCEL_REQUEST_BUTTON,
    IMPORT_CATALOG_BUTTON,
    IMPORT_STOCK_BUTTON,
}


# ========== Reply Keyboards ==========


def main_menu_keyboard(is_admin: bool = False):
    kb = ReplyKeyboardBuilder()
    kb.button(text=ASK_ASSISTANT_BUTTON)
    kb.button(text=SEARCH_PRODUCT_BUTTON)
    kb.button(text=CHECK_REQUEST_BUTTON)
    kb.button(text=IMPORT_STOCK_BUTTON)
    if is_admin:
        kb.button(text=ASSISTANT_DRAFTS_BUTTON)
    kb.adjust(1)
    return kb.as_markup(
        resize_keyboard=True, input_field_placeholder="Выберите действие..."
    )


def search_input_keyboard():
    kb = ReplyKeyboardBuilder()
    kb.button(text="⬅️ Назад")
    kb.button(text=MAIN_MENU_BUTTON)
    kb.adjust(2)
    return kb.as_markup(
        resize_keyboard=True, input_field_placeholder="Введите артикул или название..."
    )


def assistant_input_keyboard():
    kb = ReplyKeyboardBuilder()
    kb.button(text=MAIN_MENU_BUTTON)
    kb.adjust(1)
    return kb.as_markup(
        resize_keyboard=True,
        input_field_placeholder="Например: Есть G1017 5 шт?",
    )


def search_results_keyboard():
    kb = ReplyKeyboardBuilder()
    kb.button(text="🔎 Новый поиск")
    kb.button(text="⬅️ Назад")
    kb.button(text=MAIN_MENU_BUTTON)
    kb.adjust(2, 1)
    return kb.as_markup(
        resize_keyboard=True, input_field_placeholder="Выберите товар из списка выше..."
    )


def product_view_keyboard():
    kb = ReplyKeyboardBuilder()
    kb.button(text="⬅️ Назад")
    kb.button(text=MAIN_MENU_BUTTON)
    kb.adjust(2)
    return kb.as_markup(resize_keyboard=True)


# ========== Inline (только для выбора товара из списка) ==========


def products_inline_keyboard(products):
    kb = InlineKeyboardBuilder()
    for p in products:
        name = p["name"][:25] + "..." if len(p["name"]) > 25 else p["name"]
        sku = p.get("sku", "")[:8]
        kb.button(text=f"📦 {name} ({sku})", callback_data=f"prod:{p['id']}")

    kb.button(text="🔎 Новый поиск", callback_data="search:stay")
    kb.button(text="🏠 Главное меню", callback_data="menu:main")
    kb.adjust(1)
    return kb.as_markup()


def product_actions_inline_keyboard(product_id: int):
    return None


def search_nav_inline_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="🏠 Главное меню", callback_data="menu:main")
    kb.button(text="❌ Выйти из поиска", callback_data="search:exit")
    kb.adjust(2)
    return kb.as_markup()


def search_results_inline_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="🔎 Новый поиск", callback_data="search:stay")
    kb.button(text="🏠 Главное меню", callback_data="menu:main")
    kb.adjust(2)
    return kb.as_markup()


def product_view_inline_keyboard(product_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="🔎 Новый поиск", callback_data="search:stay")
    kb.button(text="🏠 Главное меню", callback_data="menu:main")
    kb.adjust(1)
    return kb.as_markup()


# Legacy keyboards (для совместимости с sale.py, voice.py)


def back_keyboard():
    kb = ReplyKeyboardBuilder()
    kb.button(text="◀️ Назад")
    return kb.as_markup(resize_keyboard=True)


def products_keyboard(products):
    """Legacy: inline keyboard для списка товаров"""
    kb = InlineKeyboardBuilder()
    for p in products:
        name = p["name"][:30] + "..." if len(p["name"]) > 30 else p["name"]
        sku = p.get("sku", "")[:10]
        kb.button(text=f"📦 {name} ({sku})", callback_data=f"prod:{p['id']}")
    kb.button(text="◀️ В меню", callback_data="menu:main")
    kb.adjust(1)
    return kb.as_markup()


def product_actions_keyboard(product_id: int):
    """Legacy: inline keyboard для действий с товаром"""
    kb = InlineKeyboardBuilder()
    kb.button(text="◀️ Назад к списку", callback_data="menu:back_to_products")
    kb.adjust(1)
    return kb.as_markup()


def back_to_products_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="◀️ Назад к списку", callback_data="menu:back_to_products")
    return kb.as_markup()


def sale_actions_keyboard(sale_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="📄 Получить накладную", callback_data=f"inv:{sale_id}")
    kb.button(text="◀️ В меню", callback_data="menu:main")
    kb.adjust(1)
    return kb.as_markup()


def sale_confirm_keyboard(sale_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Подтвердить", callback_data=f"sale_confirm:{sale_id}")
    kb.button(text="❌ Отменить", callback_data=f"sale_cancel:{sale_id}")
    kb.adjust(2)
    return kb.as_markup()


def check_request_inline_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Проверить заявку", callback_data="batch:check_request")
    kb.button(text="🔎 Новый поиск", callback_data="search:stay")
    kb.button(text="🏠 Главное меню", callback_data="menu:main")
    kb.adjust(1)
    return kb.as_markup()
