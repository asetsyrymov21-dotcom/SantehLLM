from collections import defaultdict

from embeddings import embed_texts, EMBEDDING_MODEL
from app.repositories.documents import (
    fetch_chunk_candidates_for_docs,
    fetch_chunks_by_indices,
    fetch_doc_candidates_by_vectors,
    fetch_document_chunks_fallback,
)
from app.services.rerank import lexical_overlap, jaccard_similarity


def expand_adjacent_chunks(tenant_id: str, matches: list[dict]) -> list[dict]:
    # --- Context expansion: add adjacent chunks ---
    doc_map = defaultdict(set)
    for m in matches:
        idx = m["chunk_index"]
        doc_map[m["document_id"]].add(idx - 1)
        doc_map[m["document_id"]].add(idx)
        doc_map[m["document_id"]].add(idx + 1)

    expanded_matches = []
    for doc_id, indices in doc_map.items():
        expanded = fetch_chunks_by_indices(
            tenant_id=tenant_id,
            document_id=doc_id,
            indices=list(indices),
        )
        expanded_matches.extend(expanded)

    # --- Deduplicate expanded chunks ---
    deduped = {}
    for m in expanded_matches:
        key = (m["document_id"], m["chunk_index"])
        if key not in deduped:
            deduped[key] = m

    return list(deduped.values())


def merge_adjacent_chunks(matches: list[dict]) -> list[dict]:
    # --- Merge adjacent chunks into contiguous blocks ---
    grouped = defaultdict(list)
    for m in matches:
        grouped[m["document_id"]].append(m)

    merged_blocks = []
    for doc_id, doc_matches in grouped.items():
        doc_matches.sort(key=lambda x: x["chunk_index"])
        if not doc_matches:
            continue

        current_group = [doc_matches[0]]

        for m in doc_matches[1:]:
            prev = current_group[-1]
            if m["chunk_index"] == prev["chunk_index"] + 1:
                current_group.append(m)
            else:
                merged_blocks.append(
                    {
                        "document_id": doc_id,
                        "start_chunk_index": current_group[0]["chunk_index"],
                        "end_chunk_index": current_group[-1]["chunk_index"],
                        "text": "\n\n".join(
                            (x.get("text") or "") for x in current_group
                        ),
                        "score": max(
                            x.get("final_score", x.get("score", 0.0))
                            for x in current_group
                        ),
                    }
                )
                current_group = [m]

        merged_blocks.append(
            {
                "document_id": doc_id,
                "start_chunk_index": current_group[0]["chunk_index"],
                "end_chunk_index": current_group[-1]["chunk_index"],
                "text": "\n\n".join((x.get("text") or "") for x in current_group),
                "score": max(
                    x.get("final_score", x.get("score", 0.0)) for x in current_group
                ),
            }
        )

    merged_blocks.sort(key=lambda x: x["score"], reverse=True)
    return merged_blocks


def build_context(
    merged_blocks: list[dict],
    max_context_chars: int,
    max_context_blocks: int,
    max_block_chars: int,
) -> str:
    # 3) Склеиваем куски в контекст, но с лимитом (чтобы модель не "захлёбывалась")
    MAX_CONTEXT_CHARS = max_context_chars
    MAX_CONTEXT_BLOCKS = max_context_blocks
    MAX_BLOCK_CHARS = max_block_chars

    context_parts = []
    total = 0

    for block in merged_blocks:
        if len(context_parts) >= MAX_CONTEXT_BLOCKS:
            break

        t = (block["text"] or "").strip()
        if not t:
            continue

        if len(t) > MAX_BLOCK_CHARS:
            t = t[:MAX_BLOCK_CHARS].rstrip()

        if not t:
            continue

        header = (
            f"[doc={block['document_id']} "
            f"chunks={block['start_chunk_index']}-{block['end_chunk_index']} "
            f"score={block['score']:.4f}]"
        )
        part = f"{header}\n{t}"

        if total + len(part) + 2 > MAX_CONTEXT_CHARS:
            remaining = MAX_CONTEXT_CHARS - total
            min_needed = len(header) + 1

            if remaining > min_needed:
                text_budget = remaining - min_needed
                clipped_text = t[:text_budget].rstrip()
                clipped_part = f"{header}\n{clipped_text}".rstrip()

                if clipped_text:
                    context_parts.append(clipped_part)
                    total += len(clipped_part) + 2
            break

        context_parts.append(part)
        total += len(part) + 2

    return "\n\n".join(context_parts)


def run_rag_retrieval(
    tenant_id: str,
    query: str,
    primary_qvec: list[float],
    top_k: int,
    document_id: int | None,
    doc_k: int,
    threshold: float,
    per_doc_vector_k: int,
    min_text_sim: float,
    max_context_chars: int,
    max_context_blocks: int,
    max_block_chars: int,
) -> dict:
    # 1) Multi-query embedding
    words = query.split()
    extra_qvecs = []

    if len(words) >= 3:
        short_query = " ".join(words[:3])
        extra_qvecs = embed_texts([short_query], model=EMBEDDING_MODEL)

    qvecs = [primary_qvec] + extra_qvecs

    DOC_K = doc_k
    DOC_VECTOR_K = DOC_K * 4  # берем больше кандидатов, потом будем rerank
    docs = fetch_doc_candidates_by_vectors(
        tenant_id=tenant_id,
        qvecs=qvecs,
        embedding_model=EMBEDDING_MODEL,
        document_id=document_id,
        limit=DOC_VECTOR_K,
    )

    selected_docs = docs[:DOC_K]
    doc_score_map = {d["doc_id"]: d["doc_score"] for d in selected_docs}
    matches = fetch_chunk_candidates_for_docs(
        tenant_id=tenant_id,
        doc_ids=[d["doc_id"] for d in selected_docs],
        qvecs=qvecs,
        embedding_model=EMBEDDING_MODEL,
        per_doc_vector_k=per_doc_vector_k,
    )

    THRESHOLD = threshold
    matches = [m for m in matches if m["score"] >= THRESHOLD]

    if not matches and document_id:
        print("FALLBACK → taking chunks from document")
        matches = fetch_document_chunks_fallback(
            tenant_id=tenant_id,
            document_id=document_id,
            limit=top_k,
        )

    # --- Гибридная пересортировка (rerank) ---
    for m in matches:
        m["lexical_score"] = lexical_overlap(query, m["text"])

    max_lex = max((m["lexical_score"] for m in matches), default=0) or 1

    for m in matches:
        norm_lex = m["lexical_score"] / max_lex
        doc_boost = doc_score_map.get(m["document_id"], 0.0)
        m["final_score"] = m["score"] * 0.6 + norm_lex * 0.2 + doc_boost * 0.2
        m["doc_boost"] = doc_boost

    matches.sort(key=lambda x: x["final_score"], reverse=True)

    # --- Diversity отбор: не берем слишком похожие куски подряд ---
    selected = []
    MIN_TEXT_SIM = min_text_sim  # чем больше, тем строже (0.45..0.70)

    for m in matches:
        ok = True
        for s in selected:
            if jaccard_similarity(m["text"], s["text"]) >= MIN_TEXT_SIM:
                ok = False
                break
        if ok:
            selected.append(m)
        if len(selected) >= top_k:
            break

    matches = selected

    matches = expand_adjacent_chunks(tenant_id=tenant_id, matches=matches)
    merged_blocks = merge_adjacent_chunks(matches=matches)
    context = build_context(
        merged_blocks=merged_blocks,
        max_context_chars=max_context_chars,
        max_context_blocks=max_context_blocks,
        max_block_chars=max_block_chars,
    )

    source_map = {}
    for m in matches:
        doc_id = m["document_id"]
        if doc_id not in source_map:
            source_map[doc_id] = {
                "source_id": f"S{len(source_map) + 1}",
                "document_id": doc_id,
                "chunk_indices": [],
            }

        chunk_index = m.get("chunk_index")
        if (
            chunk_index is not None
            and chunk_index not in source_map[doc_id]["chunk_indices"]
        ):
            source_map[doc_id]["chunk_indices"].append(chunk_index)

    sources = list(source_map.values())

    for s in sources:
        s["chunk_indices"].sort()

    return {
        "matches": matches,
        "merged_blocks": merged_blocks,
        "context": context,
        "sources": sources,
        "primary_qvec": primary_qvec,
        "meta": {
            "retrieval_k": top_k,
            "selected_chunks": len(matches),
            "context_chars": len(context),
        },
    }
