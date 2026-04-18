from __future__ import annotations

import re
from app.services.request_check.schemas import RequestLine


_QTY_PATTERNS = [
    # "G1012 x2", "G1012 *2"
    re.compile(r"^([A-Za-z0-9\-]+)\s*[x*]\s*(\d+)$", re.IGNORECASE),
    # "G1012, 2"
    re.compile(r"^([A-Za-z0-9\-]+)\s*,\s*(\d+)$", re.IGNORECASE),
    # "G1012 2"
    re.compile(r"^([A-Za-z0-9\-]+)\s+(\d+)$", re.IGNORECASE),
]


def parse_batch_sku_text(text: str) -> list[RequestLine]:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    result = []
    for raw in lines:
        result.append(_parse_line(raw))
    return result


def _parse_line(raw: str) -> RequestLine:
    for pattern in _QTY_PATTERNS:
        m = pattern.match(raw.strip())
        if m:
            sku = m.group(1).upper().strip()
            qty = max(1, int(m.group(2)))
            return RequestLine(raw=raw, sku=sku, requested_qty=qty)

    # просто SKU без количества
    sku = raw.upper().strip()
    return RequestLine(raw=raw, sku=sku, requested_qty=1)
