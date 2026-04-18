from aiogram.fsm.context import FSMContext


class UserData:
    """Минимальное хранение данных пользователя"""
    
    @classmethod
    async def get_catalog(cls, state: FSMContext) -> str | None:
        data = await state.get_data()
        return data.get("catalog")
    
    @classmethod
    async def set_catalog(cls, state: FSMContext, catalog: str | None) -> None:
        await state.update_data(catalog=catalog)
    
    @classmethod
    async def get_last_query(cls, state: FSMContext) -> str | None:
        data = await state.get_data()
        return data.get("last_query")
    
    @classmethod
    async def set_last_query(cls, state: FSMContext, query: str) -> None:
        await state.update_data(last_query=query)