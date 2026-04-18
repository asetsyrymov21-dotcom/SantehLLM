from __future__ import annotations
import re


def _debug_card_extraction(
    page_number: int,
    start_pos: int,
    end_pos: int,
    main_sku: str,
    block_text: str,
    variants: list[str],
    title_candidates: list[str],
    chosen_title: str,
) -> None:
    preview = re.sub(r"\s+", " ", block_text)[:300]
    print(
        f"[page={page_number}] card sku={main_sku} start={start_pos} end={end_pos} variants={variants}"
    )
    print(f"[page={page_number}] card sku={main_sku} preview={preview!r}")
    print(
        f"[page={page_number}] card sku={main_sku} title_candidates={title_candidates}"
    )
    print(f"[page={page_number}] card sku={main_sku} chosen_title={chosen_title!r}")
