from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api import deps
from app.schemas import SearchRequest, SearchResponse
from app.services.search import SearchService

router = APIRouter(prefix="/search", tags=["search"])


@router.post("/products", response_model=SearchResponse)
def search_products(
    payload: SearchRequest,
    service: SearchService = Depends(deps.get_search_service),
) -> SearchResponse:
    return service.search_products(payload)
