from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import AssistantQACache
from app.schemas import (
    AssistantMemoryEntry,
    AssistantMemoryListResponse,
    AssistantMemoryLookupResponse,
    AssistantMemoryStoreRequest,
)

OPERATIONAL_INTENTS = {"stock_check", "price_check"}
ALLOWED_STATUSES = {"draft", "approved", "rejected"}


class AssistantMemoryService:
    def __init__(self, session: Session):
        self.session = session

    def lookup(
        self,
        question: str,
        intent: str | None = None,
        status: str = "approved",
    ) -> AssistantMemoryLookupResponse:
        normalized = normalize_memory_question(question)
        if not normalized:
            return AssistantMemoryLookupResponse(found=False)

        stmt = select(AssistantQACache).where(
            AssistantQACache.normalized_question == normalized,
            AssistantQACache.status == status,
        )
        if intent:
            stmt = stmt.where(AssistantQACache.intent == intent)

        entry = self.session.execute(stmt).scalar_one_or_none()
        if not entry:
            return AssistantMemoryLookupResponse(found=False)

        entry.hit_count += 1
        entry.last_used_at = datetime.utcnow()
        self.session.commit()
        self.session.refresh(entry)

        return AssistantMemoryLookupResponse(
            found=True,
            entry=_to_entry_schema(entry),
        )

    def store(self, payload: AssistantMemoryStoreRequest) -> AssistantMemoryEntry:
        if payload.intent in OPERATIONAL_INTENTS:
            raise ValueError("Operational answers must not be stored in QA memory")
        if payload.status not in ALLOWED_STATUSES:
            raise ValueError(f"Unsupported QA status: {payload.status}")

        normalized = normalize_memory_question(payload.question)
        if not normalized:
            raise ValueError("Question is empty after normalization")

        existing = self.session.execute(
            select(AssistantQACache).where(
                AssistantQACache.normalized_question == normalized
            )
        ).scalar_one_or_none()

        if existing:
            existing.raw_question_example = payload.question.strip()
            existing.intent = payload.intent
            existing.answer_text = payload.answer_text.strip()
            existing.source_product_ids = payload.source_product_ids or []
            existing.source_document_ids = payload.source_document_ids or []
            existing.status = payload.status
            existing.meta_json = payload.meta_json
            entry = existing
        else:
            entry = AssistantQACache(
                normalized_question=normalized,
                raw_question_example=payload.question.strip(),
                intent=payload.intent,
                answer_text=payload.answer_text.strip(),
                source_product_ids=payload.source_product_ids or [],
                source_document_ids=payload.source_document_ids or [],
                status=payload.status,
                meta_json=payload.meta_json,
            )
            self.session.add(entry)

        self.session.commit()
        self.session.refresh(entry)
        return _to_entry_schema(entry)

    def list_entries(
        self,
        status: str = "draft",
        limit: int = 5,
        offset: int = 0,
    ) -> AssistantMemoryListResponse:
        if status not in ALLOWED_STATUSES:
            raise ValueError(f"Unsupported QA status: {status}")

        limit = max(1, min(limit, 50))
        offset = max(0, offset)

        total = self.session.execute(
            select(func.count()).select_from(AssistantQACache).where(
                AssistantQACache.status == status
            )
        ).scalar_one()
        rows = self.session.execute(
            select(AssistantQACache)
            .where(AssistantQACache.status == status)
            .order_by(AssistantQACache.updated_at.desc(), AssistantQACache.id.desc())
            .offset(offset)
            .limit(limit)
        ).scalars().all()
        return AssistantMemoryListResponse(
            total=total,
            entries=[_to_entry_schema(row) for row in rows],
        )

    def approve(self, entry_id: int) -> AssistantMemoryEntry:
        entry = self.session.get(AssistantQACache, entry_id)
        if not entry:
            raise LookupError("Assistant memory entry not found")
        if entry.intent in OPERATIONAL_INTENTS:
            raise ValueError("Operational answers must not be approved")

        entry.status = "approved"
        self.session.commit()
        self.session.refresh(entry)
        return _to_entry_schema(entry)

    def delete(self, entry_id: int) -> None:
        entry = self.session.get(AssistantQACache, entry_id)
        if not entry:
            raise LookupError("Assistant memory entry not found")

        self.session.delete(entry)
        self.session.commit()


def normalize_memory_question(question: str) -> str:
    text = (question or "").strip().lower()
    text = text.replace("ё", "е")
    text = re.sub(r"[^\w\s.-]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _to_entry_schema(entry: AssistantQACache) -> AssistantMemoryEntry:
    return AssistantMemoryEntry(
        id=entry.id,
        normalized_question=entry.normalized_question,
        raw_question_example=entry.raw_question_example,
        intent=entry.intent,
        answer_text=entry.answer_text,
        source_product_ids=entry.source_product_ids or [],
        source_document_ids=entry.source_document_ids or [],
        status=entry.status,
        hit_count=entry.hit_count,
    )
