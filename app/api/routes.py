from fastapi import APIRouter

from app.api import (
    assistant,
    documents,
    health,
    imports,
    inventory,
    products,
    rag,
    sales,
    search,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(products.router)
api_router.include_router(inventory.router)
api_router.include_router(sales.router)
api_router.include_router(search.router)
api_router.include_router(imports.router)
api_router.include_router(documents.router)
api_router.include_router(rag.router)
api_router.include_router(assistant.router)
