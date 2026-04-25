from __future__ import annotations

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models


class DocumentRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, document_id: int) -> models.Document | None:
        return self.session.get(models.Document, document_id)

    def list_by_sale(self, sale_id: int) -> Sequence[models.Document]:
        stmt = select(models.Document).where(models.Document.related_sale_id == sale_id)
        return self.session.scalars(stmt).all()

    def create(
        self,
        *,
        document_type: str,
        document_number: str,
        status: models.DocumentStatus,
        related_sale_id: int | None = None,
        file_path: str | None = None,
    ) -> models.Document:
        doc = models.Document(
            document_type=document_type,
            document_number=document_number,
            status=status,
            related_sale_id=related_sale_id,
            file_path=file_path,
        )
        self.session.add(doc)
        self.session.flush()
        return doc

    def update_file_path(self, document: models.Document, file_path: str) -> models.Document:
        document.file_path = file_path
        self.session.add(document)
        self.session.flush()
        return document
