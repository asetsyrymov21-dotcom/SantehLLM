from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api import deps
from app.schemas import (
    AssistantMemoryEntry,
    AssistantMemoryListResponse,
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


@router.get("/memory", response_model=AssistantMemoryListResponse)
def list_assistant_memory(
    status: str = "draft",
    limit: int = 5,
    offset: int = 0,
    service: AssistantMemoryService = Depends(deps.get_assistant_memory_service),
) -> AssistantMemoryListResponse:
    try:
        return service.list_entries(status=status, limit=limit, offset=offset)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/memory/{entry_id}/approve", response_model=AssistantMemoryEntry)
def approve_assistant_memory(
    entry_id: int,
    service: AssistantMemoryService = Depends(deps.get_assistant_memory_service),
) -> AssistantMemoryEntry:
    try:
        return service.approve(entry_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/memory/{entry_id}")
def delete_assistant_memory(
    entry_id: int,
    service: AssistantMemoryService = Depends(deps.get_assistant_memory_service),
) -> dict[str, bool]:
    try:
        service.delete(entry_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"ok": True}
