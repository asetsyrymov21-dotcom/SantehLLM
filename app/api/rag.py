from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api import deps
from app.schemas.utility import (
    RagQueryRequest,
    RagQueryResponse,
    RagIngestTextRequest,
    RagIngestTextResponse,
    RagAskRequest,
    RagAskResponse,
)
from app.services.rag import RagService

router = APIRouter(prefix="/rag", tags=["rag"])


@router.post("/query", response_model=RagQueryResponse)
def query_rag(
    payload: RagQueryRequest,
    service: RagService = Depends(deps.get_rag_service),
) -> RagQueryResponse:
    return service.query(payload)


@router.post("/documents/text", response_model=RagIngestTextResponse, status_code=201)
def ingest_text_document(
    payload: RagIngestTextRequest,
    service: RagService = Depends(deps.get_rag_service),
) -> RagIngestTextResponse:
    return service.ingest_text(payload)


@router.post("/ask", response_model=RagAskResponse)
def ask_rag(
    payload: RagAskRequest,
    service: RagService = Depends(deps.get_rag_service),
) -> RagAskResponse:
    return service.ask(payload)
