"""CLI script to build PDF text dump and SKU index."""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.pdf_enrichment.bootstrap import build_pdf_dump_and_index

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Build PDF text dump and SKU index")
    parser.add_argument("--pdf", required=True, help="Path to PDF catalog")
    parser.add_argument("--dump", required=True, help="Path to save page dump JSON")
    parser.add_argument("--index", required=True, help="Path to save SKU index JSON")
    parser.add_argument("--start-page", type=int, default=1, help="First page (1-indexed)")
    parser.add_argument("--end-page", type=int, default=None, help="Last page (default: all)")
    
    args = parser.parse_args()
    
    try:
        pdf_dump, sku_index = build_pdf_dump_and_index(
            pdf_path=args.pdf,
            dump_path=args.dump,
            index_path=args.index,
            start_page=args.start_page,
            end_page=args.end_page,
        )
        
        print(f"\nSuccess: {pdf_dump.page_count} pages, {len(sku_index.sku_to_pages)} SKUs")
        return 0
        
    except Exception as e:
        logger.error(f"Failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
