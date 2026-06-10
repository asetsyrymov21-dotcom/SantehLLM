from __future__ import annotations

import logging
from typing import List

from openai import OpenAI

MODEL_NAME = "text-embedding-3-small"
DIMENSION = 1536

logger = logging.getLogger(__name__)
_client = None


def _client_singleton() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


def embed_texts(texts: List[str], *, batch_size: int = 100) -> List[List[float]]:
    """Call OpenAI embedding API and return list of vectors."""
    if not texts:
        return []

    client = _client_singleton()
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        resp = client.embeddings.create(model=MODEL_NAME, input=batch)
        vectors.extend(item.embedding for item in resp.data)
    return vectors
