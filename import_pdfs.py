import sys
sys.path.insert(0, "/app")
import os
from app.utils.pdf_parser import extract_tables_from_pdf
from app.db.session import SessionLocal
from app.repositories.product import ProductRepository
from app.schemas import ProductCreate

pdf_files = [
    ("/tmp/2026 FRAP.pdf", "FRAP"),
    ("/tmp/2026 GAPPOсмесители каталог .pdf", "GAPPO"),
    ("/tmp/2026年 管阀画册.pdf", "Chinese"),
]

db = SessionLocal()
repo = ProductRepository(db)
total = 0

for pdf_path, brand_hint in pdf_files:
    if not os.path.exists(pdf_path):
        print(f"Not found: {pdf_path}")
        continue
    with open(pdf_path, "rb") as f:
        products = extract_tables_from_pdf(f.read())
    print(f"{brand_hint}: {len(products)} products")
    for p in products[:2]:
        print(f"  {p.get('sku')} - {p.get('name', '')[:50]}")
    total += len(products)

print(f"\nTotal: {total} products found")
db.close()
