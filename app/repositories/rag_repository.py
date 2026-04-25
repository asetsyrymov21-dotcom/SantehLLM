from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import rag_models
from app.utils.embeddings import embed_texts


class RagRepository:
    def __init__(self, session: Session):
        self.session = session

    def add_document_with_chunks(self, title: str, source: str | None, chunks: list[str]) -> rag_models.RagDocument:
        doc = rag_models.RagDocument(title=title, source=source)
        self.session.add(doc)
        self.session.flush()
        vectors = embed_texts(chunks)
        for idx, (text, vec) in enumerate(zip(chunks, vectors)):
            chunk = rag_models.RagChunk(
                document_id=doc.id,
                chunk_index=idx,
                text=text,
                embedding=vec,
            )
            self.session.add(chunk)
        self.session.flush()
        return doc

    def search_chunks(self, query: str, *, limit: int = 5, offset: int = 0):
        qvec = embed_texts([query])[0]
        distance = rag_models.RagChunk.embedding.op("<->")(qvec)
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
            .limit(limit)
        )
        rows = self.session.execute(stmt).all()
        return rows

    def get_chunks_by_ids(self, ids):
        stmt = select(rag_models.RagChunk).where(rag_models.RagChunk.id.in_(list(ids)))
        return self.session.scalars(stmt).all()
