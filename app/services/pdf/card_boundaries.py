from __future__ import annotations

import logging
import re

from .attribute_context import _is_attribute_context
from .classifier import is_valid_sku
from .sku_utils import _looks_like_main_product_sku
from .shared_patterns import MAIN_SKU_PATTERN

logger = logging.getLogger(__name__)


def _find_product_card_boundaries(text: str) -> list[tuple[int, int, str]]:
    """
    Find product card boundaries using SKU positions in raw text.

    Page 91 fix:
    - allow same-family variants to stay inside one block
    - open a new block on distinct base-family change
    - do NOT reject a SKU as attribute-context if its right-side text
      clearly looks like a product title/card start
    """

    def _base_family(sku: str) -> str:
        return sku.strip().upper().split("-", 1)[0]

    def _looks_like_card_start(text: str, start_pos: int, sku: str) -> bool:
        """
        Positive signal that this SKU is the start of a real product card,
        even if left_context contains 'Размер упаковки:' from previous card.
        """
        right = text[start_pos : start_pos + 120]
        right = re.sub(r"\s+", " ", right).strip()

        # Remove the SKU itself from the beginning
        if right.upper().startswith(sku.upper()):
            right = right[len(sku) :].strip(" -,:;")

        if not right:
            return False

        product_type_patterns = [
            r"^Смеситель\b",
            r"^Смеситель\s+для\b",
            r"^Встраиваемый\s+смеситель\b",
            r"^Встраиваемый\s+гигиенический\s+душ\b",
            r"^Душевая\s+система\b",
            r"^Дозатор\b",
            r"^Излив\b",
            r"^Лейка\b",
        ]

        return any(
            re.search(pattern, right, flags=re.IGNORECASE)
            for pattern in product_type_patterns
        )

    matches = list(MAIN_SKU_PATTERN.finditer(text))
    if not matches:
        return []

    candidates: list[tuple[int, str, str]] = []

    for match in matches:
        sku = match.group(1).upper()

        if not is_valid_sku(sku):
            continue

        if not _looks_like_main_product_sku(sku):
            continue

        # Old bug on page 91:
        # next-card SKU can be preceded by "... Размер упаковки: ..."
        # from previous card in the linear text stream.
        # If right context clearly looks like a title, keep it as a card start.
        if _is_attribute_context(text, match.start()) and not _looks_like_card_start(
            text, match.start(), sku
        ):
            logger.debug("Skipping attribute-context SKU %s", sku)
            continue

        candidates.append((match.start(), sku, _base_family(sku)))

    if not candidates:
        return []

    # Deduplicate exact hits while preserving order
    deduped: list[tuple[int, str, str]] = []
    seen_positions: set[tuple[int, str]] = set()

    for start_pos, sku, family in candidates:
        key = (start_pos, sku)
        if key in seen_positions:
            continue
        seen_positions.add(key)
        deduped.append((start_pos, sku, family))

    if not deduped:
        return []

    boundaries: list[tuple[int, int, str]] = []

    block_start, block_sku, block_family = deduped[0]

    for i in range(1, len(deduped)):
        start_pos, sku, family = deduped[i]

        # Same family -> keep variants inside current block
        if family == block_family:
            continue

        # Distinct family -> open a new block
        boundaries.append((block_start, start_pos, block_sku))
        block_start, block_sku, block_family = start_pos, sku, family

    boundaries.append((block_start, len(text), block_sku))

    return boundaries
