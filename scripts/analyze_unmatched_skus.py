#!/usr/bin/env python3
"""Analyze unmatched SKUs from FRAP stock import.

Reads unmatched SKU CSV report and analyzes reasons for mismatch.

Usage:
    python scripts/analyze_unmatched_skus.py --input reports/unmatched_skus.csv
    python scripts/analyze_unmatched_skus.py --input reports/unmatched_skus.csv --output reports/analysis.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.db.session import SessionLocal
from app.services.stock_import.unmatched_analyzer import UnmatchedSkuAnalyzer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze unmatched SKUs from stock import"
    )
    parser.add_argument(
        "--input",
        "-i",
        type=str,
        required=True,
        help="Path to unmatched SKUs CSV file",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Output CSV path (default: reports/unmatched_analysis_YYYYMMDD_HHMMSS.csv)",
    )
    parser.add_argument(
        "--examples",
        type=int,
        default=5,
        help="Number of examples per category to display (default: 5)",
    )
    return parser.parse_args()


def print_examples(analyses, reason: str, count: int) -> None:
    """Print example SKUs for a given reason."""
    examples = [a for a in analyses if a.probable_reason == reason][:count]
    if not examples:
        return
    
    print(f"\n  {reason.upper().replace('_', ' ')} ({len([a for a in analyses if a.probable_reason == reason])} total)")
    print("  " + "-" * 50)
    for ex in examples:
        match_info = f" -> {ex.matched_catalog_sku}" if ex.matched_catalog_sku else ""
        print(f"    {ex.source_sku:<20} {match_info}")
        if ex.notes:
            note = ex.notes[0][:60]
            print(f"      Note: {note}")


def main() -> int:
    args = parse_args()
    
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        return 1
    
    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = Path("reports") / f"unmatched_analysis_{timestamp}.csv"
    
    print("=" * 60)
    print("UNMATCHED SKU ANALYSIS")
    print("=" * 60)
    print(f"Input:  {input_path}")
    print(f"Output: {output_path}")
    print()
    
    # Run analysis
    session = SessionLocal()
    try:
        analyzer = UnmatchedSkuAnalyzer(session)
        
        print("Analyzing unmatched SKUs...")
        analyses, summary = analyzer.analyze_csv(input_path)
        
        # Export results
        analyzer.export_analysis_csv(analyses, output_path)
        
        # Print summary
        summary.print_summary()
        
        # Print examples by category
        print("\n--- EXAMPLES BY CATEGORY ---")
        for reason in ["format_mismatch", "family_or_variant_match", "real_missing", 
                       "ambiguous_match", "duplicate_catalog_candidate", "unknown"]:
            print_examples(analyses, reason, args.examples)
        
        print(f"\nDetailed analysis saved to: {output_path}")
        return 0
        
    except Exception as e:
        print(f"Error during analysis: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
