from typing import List, Dict, Any, Optional

from embeddings import embed_texts, EMBEDDING_MODEL
from app.utils.vector import vector_literal
from db import get_conn


def retrieve_chunks(
    tenant_id: str,
    query: str,
    top_k: int = 5,
    document_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Basic vector retrieval.
    Used by /query and /ask endpoints.
    """

    qvec = embed_texts([query], model=EMBEDDING_MODEL)[0]
    qvec_lit = vector_literal(qvec)

    conn = get_conn()
    cur = conn.cursor()

    try:

        if document_id is None:

            cur.execute(
                """
                SELECT
                    c.id,
                    c.document_id,
                    c.chunk_index,
                    c.text,
                    1 - (c.embedding <=> %s::vector) AS score
                FROM chunks c
                JOIN documents d
                    ON d.id = c.document_id
                    AND d.tenant_id = %s
                WHERE c.tenant_id = %s
                  AND c.embedding IS NOT NULL
                  AND c.embedding_model = %s
                ORDER BY c.embedding <=> %s::vector
                LIMIT %s;
                """,
                (qvec_lit, tenant_id, tenant_id, EMBEDDING_MODEL, qvec_lit, top_k),
            )

        else:

            cur.execute(
                """
                SELECT
                    c.id,
                    c.document_id,
                    c.chunk_index,
                    c.text,
                    1 - (c.embedding <=> %s::vector) AS score
                FROM chunks c
                JOIN documents d
                    ON d.id = c.document_id
                    AND d.tenant_id = %s
                WHERE c.tenant_id = %s
                  AND c.embedding IS NOT NULL
                  AND c.embedding_model = %s
                  AND c.document_id = %s
                ORDER BY c.embedding <=> %s::vector
                LIMIT %s;
                """,
                (
                    qvec_lit,
                    tenant_id,
                    tenant_id,
                    EMBEDDING_MODEL,
                    document_id,
                    qvec_lit,
                    top_k,
                ),
            )

        rows = cur.fetchall()

    finally:
        cur.close()
        conn.close()

    matches = [
        {
            "chunk_id": r[0],
            "document_id": r[1],
            "chunk_index": r[2],
            "text": r[3],
            "score": float(r[4]) if r[4] is not None else 0.0,
        }
        for r in rows
    ]

    return matches
