"""Fast SKU indexer for PDF catalogs with targeted extraction."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pdfplumber

from app.services.pdf.normalizer import normalize_sku, normalize_text
from .models import PdfProductMatch

logger = logging.getLogger(__name__)


@dataclass
class PageIndexEntry:
    """Index entry for a single PDF page."""

    pdf_path: Path
    page_number: int
    text_preview: str
    skus_found: list[str] = field(default_factory=list)


@dataclass
class SkuSearchResult:
    """Result of SKU search with timing info."""

    sku: str
    candidate_pages: list[tuple[str, int]]
    chosen_page: Optional[tuple[str, int]]
    match: Optional[PdfProductMatch]
    search_time_ms: float
    extract_time_ms: float


class FastPdfSkuMatcher:
    """Fast SKU matcher with pre-indexing.

    Architecture:
    1. build_index() - cheap text scan to build sku->pages map
    2. find_sku_fast() - lookup in index, then expensive extraction on candidates only
    """

    # Simple regex for SKU-like tokens (compiled once)
    # Matches: G8001, A1234, G1234-5, G1234-5B, etc.
    SKU_PATTERN = re.compile(r"\b([A-Z]\d{3,}(?:-\d{1,3}[A-Z0-9]?)?)\b", re.IGNORECASE)

    def __init__(self, pdf_paths: list[Path | str]):
        self.pdf_paths = [Path(p) for p in pdf_paths if Path(p).exists()]
        self._index: list[PageIndexEntry] = []
        self._sku_to_pages: dict[str, list[tuple[Path, int]]] = {}
        self._is_indexed = False
        logger.info(f"FastPdfSkuMatcher: {len(self.pdf_paths)} PDFs")

    def build_index(self, limit_pages: Optional[int] = None) -> None:
        """Build index of all pages with SKU occurrences.

        Uses cheap text extraction only - no expensive parsing or table extraction.

        Args:
            limit_pages: Limit indexing to first N pages per PDF (for diagnostics/smoke test)
        """
        logger.info("=" * 60)
        logger.info("START INDEXING")
        if limit_pages:
            logger.info(f"DIAGNOSTIC MODE: limiting to {limit_pages} pages per PDF")
        logger.info("=" * 60)

        self._start_time = time.time()
        total_pages_indexed = 0

        for pdf_idx, pdf_path in enumerate(self.pdf_paths, 1):
            logger.info(f"[{pdf_idx}/{len(self.pdf_paths)}] PDF: {pdf_path.name}")
            pages_indexed = self._index_pdf(
                pdf_path,
                limit_pages=limit_pages,
                global_page_offset=total_pages_indexed,
            )
            total_pages_indexed += pages_indexed

        self._is_indexed = True
        elapsed = time.time() - self._start_time

        logger.info("=" * 60)
        logger.info(
            f"INDEX COMPLETE: {total_pages_indexed} pages, {len(self._sku_to_pages)} SKUs"
        )
        logger.info(f"Total time: {elapsed:.2f}s ({elapsed*1000:.1f}ms)")
        logger.info("=" * 60)

    def _index_pdf(
        self,
        pdf_path: Path,
        limit_pages: Optional[int] = None,
        global_page_offset: int = 0,
    ) -> int:
        """Index single PDF file using cheap text extraction only.

        Args:
            pdf_path: Path to PDF file
            limit_pages: Max pages to process (None = all)
            global_page_offset: For progress reporting across multiple PDFs

        Returns:
            Number of pages indexed
        """
        pages_processed = 0
        scanned_pages = 0  # Pages with no text (likely scanned PDF)

        try:
            with pdfplumber.open(str(pdf_path)) as pdf:
                total_pages = len(pdf.pages)
                max_page = min(total_pages, limit_pages) if limit_pages else total_pages

                logger.info(f"  PDF has {total_pages} pages, will process {max_page}")

                for page_num in range(1, max_page + 1):
                    pages_processed += 1
                    global_page_num = global_page_offset + pages_processed

                    try:
                        # Cheap text extraction only - no table parsing
                        page = pdf.pages[page_num - 1]
                        raw_text = page.extract_text()

                        # Detect scanned pages (no extractable text)
                        if not raw_text or not raw_text.strip():
                            scanned_pages += 1
                            if scanned_pages <= 3 or page_num <= 3:
                                logger.warning(
                                    f"    Page {page_num}: NO TEXT (likely scanned image)"
                                )
                            continue

                        # Normalize text
                        text = normalize_text(raw_text)

                        # Find SKU-like tokens using simple regex (using class-level compiled pattern)
                        skus_found = []
                        for match in self.SKU_PATTERN.finditer(text):
                            sku = normalize_sku(match.group(1))
                            if sku and len(sku) >= 4:  # Filter out false positives
                                skus_found.append(sku)

                                # Build SKU -> pages map
                                if sku not in self._sku_to_pages:
                                    self._sku_to_pages[sku] = []
                                self._sku_to_pages[sku].append((pdf_path, page_num))

                        # Store lightweight index entry
                        self._index.append(
                            PageIndexEntry(
                                pdf_path=pdf_path,
                                page_number=page_num,
                                text_preview=text[:500],  # Shorter preview for memory
                                skus_found=skus_found,
                            )
                        )

                        # Progress log every 10 pages
                        if pages_processed % 10 == 0 or pages_processed == 1:
                            elapsed = time.time() - self._start_time
                            logger.info(
                                f"    page {page_num}/{max_page} ({global_page_num} global) - "
                                f"{len(skus_found)} SKUs, {len(text)} chars, {elapsed:.1f}s elapsed"
                            )

                    except Exception as e:
                        logger.warning(f"    Page {page_num} error: {e}")

                # Summary for this PDF
                if scanned_pages > 0:
                    logger.warning(
                        f"  WARNING: {scanned_pages}/{pages_processed} pages appear to be scanned images (no text)"
                    )

        except Exception as e:
            logger.error(f"PDF error {pdf_path}: {e}")

        return pages_processed

    def smoke_test(self, limit_pages: int = 5) -> dict:
        """Quick smoke test to verify indexer works.

        Args:
            limit_pages: Number of pages to index per PDF for quick test

        Returns:
            Dict with indexed_sku_count, pages_processed, elapsed_ms, sample_skus
        """
        logger.info("=" * 60)
        logger.info(f"SMOKE TEST: indexing {limit_pages} pages per PDF")
        logger.info("=" * 60)

        # Reset index
        self._index = []
        self._sku_to_pages = {}
        self._is_indexed = False

        start_time = time.time()
        self.build_index(limit_pages=limit_pages)
        elapsed_ms = (time.time() - start_time) * 1000

        result = {
            "indexed_sku_count": len(self._sku_to_pages),
            "pages_processed": len(self._index),
            "pdf_count": len(self.pdf_paths),
            "elapsed_ms": elapsed_ms,
            "sample_skus": list(self._sku_to_pages.keys())[:10],
        }

        # Print to stdout for immediate visibility
        print(f"\n{'='*60}")
        print(f"SMOKE TEST RESULTS:")
        print(f"  Indexed SKUs: {result['indexed_sku_count']}")
        print(f"  Pages processed: {result['pages_processed']}")
        print(f"  PDF files: {result['pdf_count']}")
        print(f"  Time: {elapsed_ms:.1f}ms")
        if result["sample_skus"]:
            print(f"  Sample SKUs: {', '.join(result['sample_skus'][:5])}")
        print(f"{'='*60}\n")

        logger.info(
            f"SMOKE TEST COMPLETE: {result['indexed_sku_count']} SKUs, {elapsed_ms:.1f}ms"
        )

        return result

    def _get_candidate_pages_with_fallback(
        self, normalized_sku: str
    ) -> tuple[list[tuple[Path, int]], list[str]]:
        """Get candidate pages with multiple normalization fallbacks.

        Returns:
            Tuple of (candidate_pages, tried_variants)
        """
        tried = []

        # Variant 1: Exact normalized SKU
        tried.append(normalized_sku)
        if normalized_sku in self._sku_to_pages:
            return self._sku_to_pages[normalized_sku], tried

        # Variant 2: Without dash variations
        if "-" in normalized_sku:
            no_dash = normalized_sku.replace("-", "")
            tried.append(no_dash)
            if no_dash in self._sku_to_pages:
                return self._sku_to_pages[no_dash], tried

        # Variant 3: With dash variations (e.g., G20079 -> G2007-9)
        if len(normalized_sku) >= 5 and normalized_sku[0].isalpha():
            # Try inserting dash before last 1-2 digits
            for dash_pos in [-2, -1]:
                if abs(dash_pos) < len(normalized_sku):
                    with_dash = (
                        normalized_sku[:dash_pos] + "-" + normalized_sku[dash_pos:]
                    )
                    tried.append(with_dash)
                    if with_dash in self._sku_to_pages:
                        return self._sku_to_pages[with_dash], tried

        # Variant 4: Case insensitive search in keys
        upper_sku = normalized_sku.upper()
        for key in self._sku_to_pages.keys():
            if key.upper() == upper_sku:
                tried.append(f"key_match:{key}")
                return self._sku_to_pages[key], tried

        return [], tried

    def find_sku_fast(self, target_sku: str, debug: bool = False) -> SkuSearchResult:
        """Fast SKU search using pre-built index.

        Args:
            target_sku: SKU to search for
            debug: If True, enable detailed debug logging
        """
        search_start = time.time()
        logger.info(f"[SKU START] {target_sku}")

        normalized = normalize_sku(target_sku)
        candidate_pages, tried_variants = self._get_candidate_pages_with_fallback(
            normalized
        )
        candidate_info = [(p.name, n) for p, n in candidate_pages]

        logger.info(f"[SKU {target_sku}] Tried variants: {tried_variants}")
        logger.info(f"[SKU {target_sku}] Candidates: {candidate_info}")

        search_time = (time.time() - search_start) * 1000

        if not candidate_pages:
            logger.info(
                f"[SKU {target_sku}] NOT FOUND in index (tried: {tried_variants})"
            )
            return SkuSearchResult(
                sku=target_sku,
                candidate_pages=[],
                chosen_page=None,
                match=None,
                search_time_ms=search_time,
                extract_time_ms=0,
            )

        extract_start = time.time()

        for pdf_path, page_num in candidate_pages:
            logger.info(f"[SKU {target_sku}] Extracting {pdf_path.name} p{page_num}")

            match, debug_info = self._extract_sku_from_page(
                pdf_path, page_num, normalized, target_sku, debug
            )

            if match:
                extract_time = (time.time() - extract_start) * 1000
                total_time = search_time + extract_time

                logger.info(f"[SKU {target_sku}] SUCCESS on p{page_num}")
                logger.info(f"[SKU {target_sku}] Title: {match.pdf_title[:50]}...")
                logger.info(
                    f"[SKU {target_sku}] Times: search={search_time:.1f}ms, "
                    f"extract={extract_time:.1f}ms, total={total_time:.1f}ms"
                )

                return SkuSearchResult(
                    sku=target_sku,
                    candidate_pages=candidate_info,
                    chosen_page=(pdf_path.name, page_num),
                    match=match,
                    search_time_ms=search_time,
                    extract_time_ms=extract_time,
                )

        extract_time = (time.time() - extract_start) * 1000
        logger.info(f"[SKU {target_sku}] FAIL - extraction failed")

        return SkuSearchResult(
            sku=target_sku,
            candidate_pages=candidate_info,
            chosen_page=None,
            match=None,
            search_time_ms=search_time,
            extract_time_ms=extract_time,
        )

    def _extract_sku_from_page(
        self,
        pdf_path: Path,
        page_num: int,
        normalized_sku: str,
        original_sku: str = "",
        debug: bool = False,
    ) -> tuple[Optional[PdfProductMatch], dict]:
        """Extract SKU data from specific page - ONLY called for candidate pages.

        This is the EXPENSIVE operation (table extraction, etc.) that should only
        be called for pages already identified as candidates by the cheap index scan.

        Returns:
            Tuple of (match, debug_info)
        """
        debug_info = {
            "requested_sku": original_sku or normalized_sku,
            "normalized_sku": normalized_sku,
            "pdf_path": pdf_path.name,
            "page_num": page_num,
            "extracted_page_skus": [],
            "tables_found": 0,
            "rows_checked": 0,
            "sku_matches_in_tables": [],
            "pdf_title": None,
            "reject_reason": None,
        }

        try:
            with pdfplumber.open(str(pdf_path)) as pdf:
                page = pdf.pages[page_num - 1]
                raw_text = page.extract_text() or ""
                text = normalize_text(raw_text)

                # Extract all SKU-like tokens from page for debug
                all_skus = set()
                for match in self.SKU_PATTERN.finditer(text):
                    sku = normalize_sku(match.group(1))
                    if sku and len(sku) >= 4:
                        all_skus.add(sku)
                debug_info["extracted_page_skus"] = sorted(list(all_skus))

                # Check if normalized_sku is in text (fuzzy check)
                sku_in_text = normalized_sku in text
                sku_in_text_upper = normalized_sku.upper() in text.upper()
                debug_info["sku_in_raw_text"] = sku_in_text
                debug_info["sku_in_text_upper"] = sku_in_text_upper

                tables = page.extract_tables()
                debug_info["tables_found"] = len(tables)

                for table_idx, table in enumerate(tables):
                    if not table or len(table) < 2:
                        continue

                    headers = [
                        str(h).lower().strip() if h else f"col_{i}"
                        for i, h in enumerate(table[0])
                    ]

                    for row_idx, row in enumerate(table[1:], 1):
                        debug_info["rows_checked"] += 1
                        row_data = {}
                        sku_value = None
                        sku_col = None

                        for i, cell in enumerate(row):
                            header = headers[i] if i < len(headers) else f"col_{i}"
                            value = str(cell).strip() if cell else ""
                            row_data[header] = value

                            # Check for SKU match with normalization
                            cell_normalized = normalize_sku(value)
                            if cell_normalized:
                                # Exact match
                                if cell_normalized == normalized_sku:
                                    sku_value = value
                                    sku_col = header
                                    debug_info["sku_matches_in_tables"].append(
                                        {
                                            "row": row_idx,
                                            "col": header,
                                            "value": value,
                                            "normalized": cell_normalized,
                                            "match_type": "exact",
                                        }
                                    )
                                # Fallback: without dash
                                elif cell_normalized.replace(
                                    "-", ""
                                ) == normalized_sku.replace("-", ""):
                                    sku_value = value
                                    sku_col = header
                                    debug_info["sku_matches_in_tables"].append(
                                        {
                                            "row": row_idx,
                                            "col": header,
                                            "value": value,
                                            "normalized": cell_normalized,
                                            "match_type": "no_dash_fallback",
                                        }
                                    )

                        if sku_value:
                            title = self._extract_title(text)
                            description = self._build_description(row_data, sku_col)
                            debug_info["pdf_title"] = title
                            debug_info["reject_reason"] = None

                            match = PdfProductMatch(
                                sku=normalized_sku,
                                pdf_title=title or "",
                                pdf_description=description,
                                source_file=pdf_path.name,
                                source_page=page_num,
                                additional_attributes=row_data,
                            )
                            return match, debug_info

                # Fallback: SKU in text but not in tables
                if normalized_sku in text or normalized_sku.upper() in text.upper():
                    title = self._extract_title(text)
                    title_source = "structured"

                    # If no structured title, try fallback from raw text context
                    if not title:
                        title = self._extract_title_from_context(
                            raw_text, normalized_sku, debug_info
                        )
                        if title:
                            title_source = "raw_text_fallback"
                            logger.debug(
                                f"[SKU {normalized_sku}] Using fallback title: {title[:50]}..."
                            )

                    debug_info["pdf_title"] = title
                    debug_info["title_source"] = title_source if title else None

                    if title:
                        debug_info["reject_reason"] = None
                        match = PdfProductMatch(
                            sku=normalized_sku,
                            pdf_title=title,
                            source_file=pdf_path.name,
                            source_page=page_num,
                        )
                        return match, debug_info
                    else:
                        debug_info["reject_reason"] = (
                            "sku_in_text_but_no_title_extracted"
                        )
                else:
                    debug_info["reject_reason"] = "sku_not_found_in_page_text"

        except Exception as e:
            debug_info["reject_reason"] = f"extraction_error: {str(e)}"
            logger.debug(f"Extraction error: {e}")

        return None, debug_info

    def find_sku_debug(self, target_sku: str) -> dict:
        """Debug run for a SKU - returns detailed diagnostic information.

        Returns dict with:
        - sku: requested SKU
        - candidate_pages: list of candidate pages
        - chosen_page: page used for extraction
        - extracted_page_skus: all SKUs found on chosen page
        - pdf_title: extracted title
        - reject_reason: why match failed
        - final_match: True/False
        """
        logger.info(f"\n{'='*70}")
        logger.info(f"DEBUG RUN FOR SKU: {target_sku}")
        logger.info(f"{'='*70}")

        normalized = normalize_sku(target_sku)
        candidate_pages, tried_variants = self._get_candidate_pages_with_fallback(
            normalized
        )

        result = {
            "sku": target_sku,
            "normalized_sku": normalized,
            "tried_variants": tried_variants,
            "candidate_pages": [(p.name, n) for p, n in candidate_pages],
            "chosen_page": None,
            "extracted_page_skus": [],
            "pdf_title": None,
            "reject_reason": None,
            "final_match": False,
            "debug_details": [],
        }

        if not candidate_pages:
            result["reject_reason"] = "no_candidate_pages_found"
            logger.info(f"  REJECT: No candidate pages found")
            logger.info(f"  Tried variants: {tried_variants}")
            return result

        # Try each candidate page
        for pdf_path, page_num in candidate_pages:
            logger.info(f"\n  Checking page: {pdf_path.name} p{page_num}")

            match, debug_info = self._extract_sku_from_page(
                pdf_path, page_num, normalized, target_sku, debug=True
            )

            result["chosen_page"] = (pdf_path.name, page_num)
            result["extracted_page_skus"] = debug_info["extracted_page_skus"]
            result["pdf_title"] = debug_info["pdf_title"]
            result["reject_reason"] = debug_info["reject_reason"]
            result["debug_details"].append(debug_info)

            logger.info(f"    Tables found: {debug_info['tables_found']}")
            logger.info(f"    Rows checked: {debug_info['rows_checked']}")
            logger.info(
                f"    SKUs on page: {debug_info['extracted_page_skus'][:10]}..."
            )
            logger.info(f"    SKU in raw text: {debug_info['sku_in_raw_text']}")
            
            # Show title extraction debug info
            if 'title_source' in debug_info:
                logger.info(f"    Title source: {debug_info.get('title_source', 'N/A')}")
            if 'rejected_candidates' in debug_info and debug_info['rejected_candidates']:
                logger.info(f"    Rejected title candidates: {len(debug_info['rejected_candidates'])}")
                for rc in debug_info['rejected_candidates'][:3]:
                    logger.info(f"      - {rc.get('reason')}: {rc.get('line', '')[:50]}...")

            if match:
                result["final_match"] = True
                result["reject_reason"] = None
                logger.info(f"    MATCH FOUND!")
                logger.info(f"    Title: {match.pdf_title[:60]}...")
                return result
            else:
                logger.info(f"    No match - reason: {debug_info['reject_reason']}")

        # All candidates exhausted
        if not result["reject_reason"]:
            result["reject_reason"] = "all_candidate_pages_exhausted"

        logger.info(
            f"\n  FINAL RESULT: No match after {len(candidate_pages)} candidate pages"
        )
        logger.info(f"{'='*70}\n")

        return result

    def debug_batch(self, skus: list[str]) -> list[dict]:
        """Debug multiple SKUs and print results table.

        Usage:
            matcher.debug_batch(["G2007-3", "G7206-29", "G4399-83"])
        """
        results = []
        print(f"\n{'='*100}")
        print(f"BATCH DEBUG RUN: {len(skus)} SKUs")
        print(f"{'='*100}")
        print(
            f"{'SKU':<15} {'Candidates':<20} {'Page':<6} {'Page SKUs':<10} {'Title':<25} {'Reject Reason':<30} {'Match'}"
        )
        print("-" * 100)

        for sku in skus:
            debug_result = self.find_sku_debug(sku)
            results.append(debug_result)

            # Format for table
            candidates = (
                str(debug_result["candidate_pages"][:1])[:18]
                if debug_result["candidate_pages"]
                else "[]"
            )
            chosen_page = (
                f"p{debug_result['chosen_page'][1]}"
                if debug_result["chosen_page"]
                else "N/A"
            )
            page_sku_count = len(debug_result["extracted_page_skus"])
            title = (debug_result["pdf_title"] or "N/A")[:23]
            reason = (debug_result["reject_reason"] or "N/A")[:28]
            match = "YES" if debug_result["final_match"] else "NO"

            print(
                f"{sku:<15} {candidates:<20} {chosen_page:<6} {page_sku_count:<10} {title:<25} {reason:<30} {match}"
            )

        print(f"{'='*100}\n")

        # Summary
        matched = sum(1 for r in results if r["final_match"])
        print(
            f"SUMMARY: {matched}/{len(skus)} SKUs matched ({matched/len(skus)*100:.1f}%)"
        )

        # List unmatched with reasons
        unmatched = [
            (r["sku"], r["reject_reason"]) for r in results if not r["final_match"]
        ]
        if unmatched:
            print("\nUNMATCHED SKUs:")
            for sku, reason in unmatched:
                print(f"  - {sku}: {reason}")

        print()
        return results

    def _extract_title(self, text: str) -> Optional[str]:
        """Quick title extraction."""
        if not text:
            return None

        lines = [l.strip() for l in text.split("\n") if l.strip()]

        title_match = re.search(
            r"^([A-Z]\d+[^\n]{0,60})\s+���\.\s*\d+", text, re.MULTILINE | re.IGNORECASE
        )
        if title_match:
            return title_match.group(1).strip()[:100]

        for line in lines[:10]:
            if any(
                ind in line.lower()
                for ind in ["���������", "����", "�����", "������", "�����"]
            ):
                if 10 < len(line) < 150:
                    return line[:100]

        for line in lines[:5]:
            if 15 < len(line) < 100:
                return line[:100]

        return None

    def _extract_title_from_context(
        self, raw_text: str, normalized_sku: str, debug_info: dict = None
    ) -> Optional[str]:
        """Extract title from raw text context around SKU.

        Prioritizes series headers and filters out SKU-only lines.
        """
        if not raw_text:
            return None

        if debug_info is None:
            debug_info = {}

        import re

        rejected_candidates = []

        def is_valid_title(line: str) -> tuple[bool, str]:
            """Check if line is a valid title (not SKU list)."""
            if not line or len(line) < 10:
                return False, "too_short"
            if len(line) > 200:
                return False, "too_long"

            tokens = line.split()
            sku_pattern = re.compile(
                r"^[A-Z]\d{3,}(-\d{1,3}[A-Z0-9]?)?$", re.IGNORECASE
            )
            sku_count = sum(1 for t in tokens if sku_pattern.match(t))

            if tokens and sku_count / len(tokens) > 0.5:
                return False, f"mostly_skus({sku_count}/{len(tokens)})"
            if sku_count >= 3 and sku_count >= len(tokens) * 0.7:
                return False, f"sku_list({sku_count}skus)"

            return True, "ok"

        lines_list = raw_text.split(chr(10))
        lines_list = [l.strip() for l in lines_list if l.strip()]

        sku_line_idx = -1
        for i, line in enumerate(lines_list):
            if normalized_sku in line.upper():
                sku_line_idx = i
                break

        if sku_line_idx == -1:
            debug_info["title_search_status"] = "sku_line_not_found"
            return None

        debug_info["sku_line_idx"] = sku_line_idx
        debug_info["sku_line_content"] = lines_list[sku_line_idx][:100]

        # Strategy 1: Find "Seriya"
        for i in range(sku_line_idx, max(-1, sku_line_idx - 15), -1):
            line = lines_list[i]
            is_valid, reason = is_valid_title(line)
            if not is_valid:
                rejected_candidates.append(
                    {"line": line[:80], "reason": reason, "strategy": "seriya"}
                )
                continue
            if re.search(r"Seriya|SERIYA", line, re.IGNORECASE):
                debug_info["title_source"] = "seriya_header"
                debug_info["chosen_title_line"] = i
                debug_info["rejected_candidates"] = rejected_candidates
                return line[:100]

        # Strategy 2: Product keywords
        keywords = ["smesitel", "latun", "nerzh", "kran", "dush"]
        for i in range(sku_line_idx, max(-1, sku_line_idx - 10), -1):
            line = lines_list[i]
            is_valid, reason = is_valid_title(line)
            if not is_valid:
                rejected_candidates.append(
                    {"line": line[:80], "reason": reason, "strategy": "keyword"}
                )
                continue
            if any(kw in line.lower() for kw in keywords):
                debug_info["title_source"] = "product_keyword"
                debug_info["chosen_title_line"] = i
                debug_info["rejected_candidates"] = rejected_candidates
                return line[:100]

        # Strategy 3: Remove SKUs from line and use context
        sku_line = lines_list[sku_line_idx]
        clean = re.sub(
            r"[A-Z]\d{3,}(-\d{1,3}[A-Z0-9]?)?", "", sku_line, flags=re.IGNORECASE
        )
        clean = re.sub(r"\s+", " ", clean).strip()
        if len(clean) > 10:
            title = f"{normalized_sku} {clean[:80]}"
            debug_info["title_source"] = "sku_line_context"
            debug_info["chosen_title_line"] = sku_line_idx
            debug_info["rejected_candidates"] = rejected_candidates
            return title

        rejected_candidates.append(
            {"line": sku_line[:80], "reason": "no_context", "strategy": "sku_line"}
        )
        debug_info["title_search_status"] = "no_valid_title"
        debug_info["rejected_candidates"] = rejected_candidates
        return None

    def _build_description(self, row_data: dict, exclude_col: str) -> str:
        """Build description from table row."""
        parts = []
        for key, value in row_data.items():
            if key != exclude_col and value:
                parts.append(f"{key}: {value}")
        return "\n".join(parts) if parts else ""
