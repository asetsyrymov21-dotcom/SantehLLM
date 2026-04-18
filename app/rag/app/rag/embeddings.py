"""
Lightweight embedding helpers reused from the old RAG backend.

Differences vs the legacy version:
- no global DB/tenant coupling
- model name, base_url and API key pulled from env/config
- reusable client + small helpers for query embedding
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Iterable, Sequence

from openai import OpenAI

# Configurable via environment; keep safe defaults for development.
DEFAULT_EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")  # allows Azure / proxy usage


@lru_cache(maxsize=1)
def get_client() -> OpenAI:
    """
    Lazily instantiates the OpenAI client.
    Uses lru_cache instead of a module-level mutable global.
    """
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set")

    client_kwargs = {"api_key": OPENAI_API_KEY}
    if OPENAI_BASE_URL:
        client_kwargs["base_url"] = OPENAI_BASE_URL

    return OpenAI(**client_kwargs)


def embed_texts(
    texts: Sequence[str] | Iterable[str],
    *,
    model: str | None = None,
) -> list[list[float]]:
    """
    Batch-embeds texts. Keeps interface close to the legacy code.
    """
    text_list = list(texts)
    if not text_list:
        return []

    use_model = model or DEFAULT_EMBEDDING_MODEL
    resp = get_client().embeddings.create(model=use_model, input=text_list)
    return [item.embedding for item in resp.data]


def embed_query(
    query: str,
    *,
    model: str | None = None,
) -> list[float]:
    """
    Convenience wrapper for single-query embedding.
    """
    vectors = embed_texts([query], model=model)
    return vectors[0] if vectors else []
