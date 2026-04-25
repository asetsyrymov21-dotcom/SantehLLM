from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path

from app.api import deps
from app.schemas import DocumentRead
from app.services.document import DocumentService

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/invoice/{sale_id}", response_model=DocumentRead, status_code=201)
def create_invoice(
    sale_id: int,
    service: DocumentService = Depends(deps.get_document_service),
) -> DocumentRead:
    doc = service.create_invoice_for_sale(sale_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Sale not found")
    return doc


@router.get("/{document_id}/download")
def download_document(
    document_id: int,
    service: DocumentService = Depends(deps.get_document_service),
):
    try:
        file_path, filename = service.get_document_file(document_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return FileResponse(path=file_path, filename=filename, media_type="application/octet-stream")
