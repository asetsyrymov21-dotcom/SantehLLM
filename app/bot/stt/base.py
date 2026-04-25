from __future__ import annotations

from typing import Protocol


class STTProvider(Protocol):
    async def recognize(self, data: bytes, *, mime_type: str | None = None) -> str:
        ...
