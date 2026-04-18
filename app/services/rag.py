from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.repositories.rag_repository import RagRepository
from app.schemas.utility import (
    RagQueryRequest,
    RagQueryResponse,
    RagQueryHit,
    RagSource,
    RagIngestTextRequest,
    RagIngestTextResponse,
    RagAskRequest,
    RagAskResponse,
)
from app.utils.chunk import normalize_text, chunk_text
from app.utils.llm import generate_rag_answer

MAX_CONTEXT_CHARS = 8000


class RagService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = RagRepository(session)

    def query(self, payload: RagQueryRequest) -> RagQueryResponse:
        rows = self.repo.search_chunks(payload.query, limit=payload.limit, offset=payload.offset)
        hits = [
            RagQueryHit(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                document_title=doc_title,
                document_source=doc_source,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                score=float(distance) * -1.0,  # smaller dist -> higher score
            )
            for chunk, doc_title, doc_source, distance in rows
        ]
        return RagQueryResponse(total=len(hits), hits=hits)

    def ingest_text(self, payload: RagIngestTextRequest) -> RagIngestTextResponse:
        text = normalize_text(payload.text)
        if not text:
            raise HTTPException(status_code=400, detail="Text is empty after normalization")

        chunk_size = payload.chunk_size or 1000
        chunk_overlap = payload.chunk_overlap if payload.chunk_overlap is not None else 200

        chunks = chunk_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        if not chunks:
            raise HTTPException(status_code=400, detail="No chunks produced from text")

        doc = self.repo.add_document_with_chunks(payload.title, payload.source, chunks)
        self.session.commit()

        return RagIngestTextResponse(
            document_id=doc.id,
            title=doc.title,
            source=doc.source,
            chunks_count=len(chunks),
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    def ask(self, request: RagAskRequest) -> RagAskResponse:
        query = request.query.strip()
        if not query:
            raise HTTPException(status_code=400, detail="Query must not be empty")

        rows = self.repo.search_chunks(query, limit=request.limit, offset=request.offset)
        hits = [
            RagQueryHit(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                document_title=doc_title,
                document_source=doc_source,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                score=float(distance) * -1.0,
            )
            for chunk, doc_title, doc_source, distance in rows
        ]

        if not hits:
            return RagAskResponse(
                query=query,
                answer="В загруженных документах подходящий ответ не найден.",
                matches=[],
                sources=[],
            )

        merged_blocks, sources = self._merge_hits(hits)
        context = self._build_context(merged_blocks)
        answer = generate_rag_answer(query=query, context=context)
        return RagAskResponse(query=query, answer=answer, matches=hits, sources=sources)

    def _merge_hits(self, hits: list[RagQueryHit]):
        blocks = []
        sources_map: dict[int, RagSource] = {}

        # group by document
        by_doc: dict[int, list[RagQueryHit]] = {}
        for h in hits:
            by_doc.setdefault(h.document_id, []).append(h)

        for doc_id, doc_hits in by_doc.items():
            doc_hits.sort(key=lambda x: x.chunk_index)
            current_group: list[RagQueryHit] = []

            def flush_group():
                if not current_group:
                    return
                text = "\n\n".join([h.text for h in current_group])
                chunk_indices = [h.chunk_index for h in current_group]
                blocks.append({
                    "document_id": doc_id,
                    "document_title": current_group[0].document_title,
                    "document_source": current_group[0].document_source,
                    "chunk_indices": chunk_indices,
                    "text": text,
                })
                source = sources_map.get(doc_id)
                if source is None:
                    sources_map[doc_id] = RagSource(
                        document_id=doc_id,
                        document_title=current_group[0].document_title or "",
                        document_source=current_group[0].document_source,
                        chunk_indices=chunk_indices,
                    )
                else:
                    source.chunk_indices.extend(chunk_indices)

            for h in doc_hits:
                if not current_group:
                    current_group = [h]
                    continue
                prev = current_group[-1]
                if h.chunk_index == prev.chunk_index + 1:
                    current_group.append(h)
                else:
                    flush_group()
                    current_group = [h]
            flush_group()

        # deduplicate and sort chunk indices inside sources
        for src in sources_map.values():
            src.chunk_indices = sorted(set(src.chunk_indices))

        return blocks, list(sources_map.values())

    def _build_context(self, blocks) -> str:
        parts: list[str] = []
        total_len = 0
        for b in blocks:
            if b["chunk_indices"]:
                if len(b["chunk_indices"]) == 1:
                    chunk_label = f"Chunks: {b['chunk_indices'][0]}"
                else:
                    chunk_label = f"Chunks: {b['chunk_indices'][0]}-{b['chunk_indices'][-1]}"
            else:
                chunk_label = "Chunks: n/a"
            title = b["document_title"] or "N/A"
            source = b["document_source"]
            header = f"[Document: {title}]\n"
            if source:
                header += f"[Source: {source}]\n"
            header += f"[{chunk_label}]"
            block_text = f"{header}\n{b['text']}\n"
            if total_len + len(block_text) > MAX_CONTEXT_CHARS:
                break
            parts.append(block_text)
            total_len += len(block_text)
        return "\n---\n".join(parts)
