"""
Shared schemas and ORM models for the search module.

Notes:
- Uses the project-wide Base from app.db.base (single declarative registry).
- Embedding column prefers pgvector; non-Postgres fallback is marked dev-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Any

from sqlalchemy import (
    Text,
    String,
    Integer,
    Float,
    func,
    Index,
    JSON,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base  # single shared Base

try:
    from pgvector.sqlalchemy import Vector  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    Vector = None


class ProductEmbedding(Base):
    __tablename__ = "product_embeddings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    tenant_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)

    # Prefer pgvector; dev-only fallback for local/non-Postgres runs.
    if Vector is not None:
        embedding: Mapped[Any] = mapped_column(Vector(None), nullable=False)
    else:  # pragma: no cover - dev fallback, not for production
        embedding: Mapped[list[float]] = mapped_column(
            JSON, nullable=False, comment="DEV-ONLY fallback when pgvector is unavailable"
        )

    searchable_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index(
            "ix_product_embeddings_product_tenant",
            "product_id",
            "tenant_id",
            unique=True,
        ),
    )


# --- DTOs used by search services ---


@dataclass(slots=True)
class ProductSearchHit:
    product_id: int
    score: float
    searchable_text: str
    source: str  # e.g. "semantic" / "keyword"


@dataclass(slots=True)
class DocumentChunkHit:
    chunk_id: int
    document_id: int
    text: str
    score: float
    metadata: Optional[dict] = None
