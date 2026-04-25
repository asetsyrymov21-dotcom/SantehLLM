from aiogram.fsm.state import StatesGroup, State


class UserFlow(StatesGroup):
    main_menu = State()
    search_input = State()
    search_results = State()
    product_view = State()


class SaleStates(StatesGroup):
    waiting_quantity = State()
    waiting_confirmation = State()


class BatchSKUStates(StatesGroup):
    awaiting_input = State()
    awaiting_excel_file = State()


class StockImportStates(StatesGroup):
    awaiting_stock_file = State()
