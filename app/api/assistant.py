from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api import deps
from app.schemas import (
    AssistantMemoryEntry,
    AssistantMemoryLookupRequest,
    AssistantMemoryLookupResponse,
    AssistantMemoryStoreRequest,
)
from app.services.assistant_memory import AssistantMemoryService

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("/memory/lookup", response_model=AssistantMemoryLookupResponse)
def lookup_assistant_memory(
    payload: AssistantMemoryLookupRequest,
    service: AssistantMemoryService = Depends(deps.get_assistant_memory_service),
) -> AssistantMemoryLookupResponse:
    return service.lookup(
        question=payload.question,
        intent=payload.intent,
        status=payload.status,
    )


@router.post("/memory/store", response_model=AssistantMemoryEntry, status_code=201)
def store_assistant_memory(
    payload: AssistantMemoryStoreRequest,
    service: AssistantMemoryService = Depends(deps.get_assistant_memory_service),
) -> AssistantMemoryEntry:
    try:
        return service.store(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
