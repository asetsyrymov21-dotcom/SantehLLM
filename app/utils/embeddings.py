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


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Call OpenAI embedding API and return list of vectors."""
    client = _client_singleton()
    resp = client.embeddings.create(model=MODEL_NAME, input=texts)
    vectors = [item.embedding for item in resp.data]
    return vectors
