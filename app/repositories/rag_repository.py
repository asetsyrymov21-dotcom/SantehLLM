from __future__ import annotations

import re
from typing import Any

from sqlalchemy import Float, literal, select
from sqlalchemy.orm import Session

from app.db import rag_models
from app.utils.embeddings import embed_texts
from app.utils.sku_utils import normalize_sku


ARTICLE_PATTERN = re.compile(
    r"\b([A-Za-zА-Яа-я]?\d?[A-Za-z][A-Za-z0-9.-]*\d[A-Za-z0-9.-]*)\b"
)


class RagRepository:
    def __init__(self, session: Session):
        self.session = session

    def add_document_with_chunks(
        self,
        title: str,
        source: str | None,
        chunks: list[str],
        metadatas: list[dict[str, Any] | None] | None = None,
    ) -> rag_models.RagDocument:
        if metadatas is not None and len(metadatas) != len(chunks):
            raise ValueError("metadatas length must match chunks length")

        doc = rag_models.RagDocument(title=title, source=source)
        self.session.add(doc)
        self.session.flush()
        vectors = embed_texts(chunks)
        if len(vectors) != len(chunks):
            raise RuntimeError("embedding count does not match chunks count")

        for idx, (text, vec) in enumerate(zip(chunks, vectors)):
            chunk = rag_models.RagChunk(
                document_id=doc.id,
                chunk_index=idx,
                text=text,
                embedding=vec,
                metadata_json=metadatas[idx] if metadatas is not None else None,
            )
            self.session.add(chunk)
        self.session.flush()
        return doc

    def search_chunks(self, query: str, *, limit: int = 5, offset: int = 0):
        exact_rows = []
        exact_article = _extract_article(query)
        if exact_article and offset == 0:
            exact_stmt = (
                select(
                    rag_models.RagChunk,
                    rag_models.RagDocument.title,
                    rag_models.RagDocument.source,
                    literal(0.0, type_=Float).label("distance"),
                )
                .join(rag_models.RagDocument, rag_models.RagChunk.document_id == rag_models.RagDocument.id)
                .where(rag_models.RagChunk.metadata_json["article"].as_string() == exact_article)
                .limit(limit)
            )
            exact_rows = self.session.execute(exact_stmt).all()
            if len(exact_rows) >= limit:
                return exact_rows

        qvec = embed_texts([query])[0]
        distance = rag_models.RagChunk.embedding.op("<->", return_type=Float)(qvec)
        stmt = (
            select(
                rag_models.RagChunk,
                rag_models.RagDocument.title,
                rag_models.RagDocument.source,
                distance.label("distance"),
            )
            .join(rag_models.RagDocument, rag_models.RagChunk.document_id == rag_models.RagDocument.id)
            .order_by(distance)
            .offset(offset)
            .limit(limit - len(exact_rows))
        )
        if exact_rows:
            exact_ids = [row[0].id for row in exact_rows]
            stmt = stmt.where(rag_models.RagChunk.id.not_in(exact_ids))
        rows = self.session.execute(stmt).all()
        return [*exact_rows, *rows]

    def get_chunks_by_ids(self, ids):
        stmt = select(rag_models.RagChunk).where(rag_models.RagChunk.id.in_(list(ids)))
        return self.session.scalars(stmt).all()

    def get_chunk_rows_by_articles(self, articles: list[str]):
        if not articles:
            return []

        stmt = (
            select(
                rag_models.RagChunk,
                rag_models.RagDocument.title,
                rag_models.RagDocument.source,
                literal(0.0, type_=Float).label("distance"),
            )
            .join(rag_models.RagDocument, rag_models.RagChunk.document_id == rag_models.RagDocument.id)
            .where(rag_models.RagChunk.metadata_json["article"].as_string().in_(articles))
        )
        rows = self.session.execute(stmt).all()
        order = {article: index for index, article in enumerate(articles)}
        return sorted(
            rows,
            key=lambda row: order.get((row[0].metadata_json or {}).get("article"), len(order)),
        )


def _extract_article(query: str) -> str | None:
    for match in ARTICLE_PATTERN.finditer(query or ""):
        normalized = normalize_sku(match.group(1))
        if normalized and any(ch.isalpha() for ch in normalized) and any(ch.isdigit() for ch in normalized):
            return normalized
    return None
