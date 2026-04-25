from pathlib import Path

from app.services.pdf.extractor import (
    extract_text_from_page,
    extract_catalog_grids_from_page,
)

BASE_DIR = Path(__file__).resolve().parent.parent
PDF_PATH = BASE_DIR / "2026 GAPPOсмесители каталог .pdf"
PAGE_NUMBER = 51

print("PDF_PATH =", PDF_PATH)
print("EXISTS =", PDF_PATH.exists())
print("PAGE_NUMBER =", PAGE_NUMBER)

print("=== TEXT ===")
text = extract_text_from_page(PDF_PATH, PAGE_NUMBER)
print(text[:3000])

print("\n=== CATALOG GRIDS ===")
blocks = extract_catalog_grids_from_page(
    PDF_PATH,
    PAGE_NUMBER,
    brand_hint="GAPPO",
    source_file=str(PDF_PATH),
)

print("blocks:", len(blocks))
for idx, block in enumerate(blocks, start=1):
    print(f"\n--- BLOCK {idx} ---")
    print(block.to_dict())
