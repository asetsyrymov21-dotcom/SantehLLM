from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RequestLine:
    raw: str
    sku: str
    requested_qty: int = 1


@dataclass
class CheckedLine:
    input_sku: str
    requested_qty: int
    found: bool
    sku: Optional[str] = None
    name: Optional[str] = None
    brand: Optional[str] = None
    stock_qty: int = 0
    status: str = "Не найден"
