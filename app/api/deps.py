from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.services.product import ProductService
from app.services.inventory import InventoryService
from app.services.sales import SalesService
from app.services.search import SearchService
from app.services.document import DocumentService
from app.services.import_service import ImportService
from app.services.rag import RagService
from app.services.assistant_memory import AssistantMemoryService


def get_session() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


SessionDep = Annotated[Session, Depends(get_session)]


def get_product_service(session: SessionDep) -> ProductService:
    return ProductService(session)


def get_inventory_service(session: SessionDep) -> InventoryService:
    return InventoryService(session)


def get_sales_service(session: SessionDep) -> SalesService:
    return SalesService(session)


def get_search_service(session: SessionDep) -> SearchService:
    return SearchService(session)


def get_document_service(session: SessionDep) -> DocumentService:
    return DocumentService(session)


def get_import_service(session: SessionDep) -> ImportService:
    return ImportService(session)


def get_rag_service(session: SessionDep) -> RagService:
    return RagService(session)


def get_assistant_memory_service(session: SessionDep) -> AssistantMemoryService:
    return AssistantMemoryService(session)
