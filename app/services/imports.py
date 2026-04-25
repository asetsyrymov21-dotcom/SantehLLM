from __future__ import annotations

from sqlalchemy.orm import Session

from app.schemas import ImportRequest, ImportResponse, ImportResult


class ImportService:
    def __init__(self, session: Session):
        self.session = session

    def import_catalog(self, payload: ImportRequest) -> ImportResponse:
        results = [ImportResult(index=i, ok=True) for i, _ in enumerate(payload.items)]
        return ImportResponse(
            total=len(payload.items),
            processed=len(payload.items),
            succeeded=len(payload.items),
            failed=0,
            results=results,
        )

    def import_inventory(self, payload: ImportRequest) -> ImportResponse:
        # Stub identical to catalog for now
        return self.import_catalog(payload)
