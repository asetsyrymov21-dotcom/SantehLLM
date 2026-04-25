"""
Document/knowledge-base retrieval adapted from the legacy chunk-based flow.
Kept separate from product search to avoid coupling.
"""

from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.rag.embeddings import embed_texts, DEFAULT_EMBEDDING_MODEL
from app.rag.rerank import lexical_overlap, jaccard_similarity
from app.rag.schemas import DocumentChunkHit


def retrieve_document_chunks(
    session: Session,
    query: str,
    *,
    tenant_id: str,
    document_id: Optional[int] = None,
    top_k: int = 5,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    min_text_sim: float = 0.55,
) -> list[DocumentChunkHit]:
    """
    Simple vector + lexical rerank for chunks.
    Expects table `document_chunks` with columns:
      id, document_id, tenant_id, embedding, embedding_model, text
    """
    if not query:
        return []

    qvec = embed_texts([query], model=embedding_model)[0]

    stmt = text(
        """
        SELECT
            id,
            document_id,
            text,
            1 - (embedding <=> :qvec) AS score
        FROM document_chunks
        WHERE tenant_id = :tenant_id
          AND embedding_model = :embedding_model
          AND embedding IS NOT NULL
          AND (:document_id IS NULL OR document_id = :document_id)
        ORDER BY embedding <=> :qvec
        LIMIT :limit;
        """
    )

    rows = session.execute(
        stmt,
        {
            "qvec": list(qvec),
            "tenant_id": tenant_id,
            "document_id": document_id,
            "embedding_model": embedding_model,
            "limit": top_k * 4,
        },
    ).all()

    hits = [
        DocumentChunkHit(
            chunk_id=r[0],
            document_id=r[1],
            text=r[2],
            score=float(r[3]) if r[3] is not None else 0.0,
        )
        for r in rows
    ]

    # lexical rerank + diversity (lighter weight than product)
    max_lex = max((lexical_overlap(query, h.text) for h in hits), default=1)
    reranked: list[DocumentChunkHit] = []
    for h in hits:
        lex = lexical_overlap(query, h.text)
        norm_lex = lex / max_lex if max_lex else 0.0
        h.score = h.score * 0.7 + norm_lex * 0.3
        reranked.append(h)

    reranked.sort(key=lambda x: x.score, reverse=True)

    selected: list[DocumentChunkHit] = []
    for h in reranked:
        if any(jaccard_similarity(h.text, s.text) >= min_text_sim for s in selected):
            continue
        selected.append(h)
        if len(selected) >= top_k:
            break

    return selected
