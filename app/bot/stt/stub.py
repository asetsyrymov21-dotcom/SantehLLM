from __future__ import annotations

from app.bot.stt.base import STTProvider


class StubSTT(STTProvider):
    async def recognize(self, data: bytes, *, mime_type: str | None = None) -> str:
        # Stub implementation: just return a fixed text length-limited summary
        text = "(voice)"
        return text
