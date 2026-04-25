#!/usr/bin/env python3
"""
Santeh PDF Extraction Regression Harness.

Compares current extraction output against expected baseline.

Usage:
    # Run full regression set
    python tools/run_santeh_regression.py --pdf "2026 GAPPOсмесители каталог .pdf" --brand GAPPO

    # Run specific pages
    python tools/run_santeh_regression.py --pdf "catalog.pdf" --brand GAPPO --pages 91,97,123

    # Use profile
    python tools/run_santeh_regression.py --pdf "catalog.pdf" --brand GAPPO --profile santeh-core
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

load_dotenv(project_root / ".env")

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


ACTION_LINE_RE = re.compile(
    r"\b(?:SKIPPED|UPDATED|CREATED)\s+page=(?P<page>\d+)\s+sku=(?P<sku>[A-Z0-9\-]+)\b"
)


def norm_sku(value: str) -> str:
    return value.strip().upper().replace("—", "-").replace("–", "-")


BASELINE_PATH = (
    Path(__file__).parent.parent
    / "tests"
    / "regression"
    / "santeh_expected_titles.json"
)

PROFILES = {
    "santeh-core": [115, 123, 134, 138],
}


@dataclass
class ExtractionResult:
    """Single extraction result from dry-run."""

    page: int
    sku: str
    action: str  # created, updated, skipped
    issue_type: str | None
    old_name: str | None
    new_name: str | None


@dataclass
class RegressionCase:
    """Expected case from baseline."""

    sku: str
    expected_name: str
    expected_status: str
    note: str = ""


@dataclass
class RegressionOutcome:
    """Outcome for a single case."""

    page: int
    sku: str
    expected: RegressionCase
    actual: ExtractionResult | None
    status: str  # IMPROVED, UNCHANGED, REGRESSED, NEW_DEFECT, MISSING
    detail: str = ""


@dataclass
class RegressionReport:
    """Full regression report."""

    improved: list[RegressionOutcome] = field(default_factory=list)
    unchanged: list[RegressionOutcome] = field(default_factory=list)
    regressed: list[RegressionOutcome] = field(default_factory=list)
    historical_only: list[RegressionOutcome] = field(default_factory=list)
    new_defects: list[RegressionOutcome] = field(default_factory=list)
    missing: list[RegressionOutcome] = field(default_factory=list)

    def has_failures(self) -> bool:
        """Check if any must_pass/stable cases failed or are missing."""
        for r in self.regressed:
            if r.expected.expected_status in ("must_pass", "stable"):
                return True
        for r in self.missing:
            if r.expected.expected_status in ("must_pass", "stable"):
                return True
        for _ in self.new_defects:
            return True
        return False


def load_baseline() -> dict[int, list[RegressionCase]]:
    """Load expected cases from baseline JSON."""
    if not BASELINE_PATH.exists():
        logger.error(f"Baseline not found: {BASELINE_PATH}")
        sys.exit(1)

    with open(BASELINE_PATH, encoding="utf-8") as f:
        data = json.load(f)

    pages = {}
    for page_num_str, page_data in data.get("pages", {}).items():
        page_num = int(page_num_str)
        cases = []
        for case in page_data.get("cases", []):
            cases.append(
                RegressionCase(
                    sku=case["sku"],
                    expected_name=case["expected_name"],
                    expected_status=case["expected_status"],
                    note=case.get("note", ""),
                )
            )
        pages[page_num] = cases

    return pages


def run_dry_run_import(
    pdf_path: Path, brand: str, pages: list[int]
) -> list[ExtractionResult]:
    """Run import_extracted_products.py --dry-run and parse output."""

    all_results: list[ExtractionResult] = []

    changed_row_pattern = re.compile(
        r"page=(\d+)\s+"
        r"sku=(\S+)\s+"
        r"action=(\w+)\s+"
        r"issue_type=(\S+)\s+"
        r"old_name=(.*?)\s+"
        r"new_name=(.*)$"
    )

    for page in pages:
        found_by_action: dict[str, ExtractionResult] = {}
        cmd = [
            sys.executable,
            "scripts/import_extracted_products.py",
            "--pdf",
            str(pdf_path),
            "--brand",
            brand,
            "--pages",
            str(page),
            "--dry-run",
        ]

        logger.info(f"Running: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={
                **os.environ,
                "PYTHONIOENCODING": "utf-8",
                "PYTHONUTF8": "1",
            },
        )

        stdout = result.stdout or ""
        stderr = result.stderr or ""
        raw_output = "\n".join(
            part for part in [stdout, stderr] if part and part.strip()
        )

        lines = raw_output.splitlines()

        for line in lines:
            m = ACTION_LINE_RE.search(line)
            if not m:
                continue

            sku = norm_sku(m.group("sku"))
            action = m.group(0).split()[0].lower()

            found_by_action[sku] = ExtractionResult(
                page=int(m.group("page")),
                sku=sku,
                action=action,
                issue_type=None,
                old_name=None,
                new_name=None,
            )

        start_idx = None
        for i, line in enumerate(lines):
            if line.strip() == "CHANGED ROWS REVIEW:":
                start_idx = i + 1
                break

        if start_idx is None:
            logger.warning(f"Page {page}: no CHANGED ROWS REVIEW found")
            logger.warning(f"Page {page}: returncode={result.returncode}")
            all_results.extend(found_by_action.values())
            continue

        section_lines: list[str] = []
        for line in lines[start_idx:]:
            stripped = line.strip()

            if not stripped:
                continue

            if stripped.startswith("page="):
                section_lines.append(stripped)
                continue

            if stripped.startswith("⚠️") or stripped.startswith("="):
                break

        for line in section_lines:
            match = changed_row_pattern.match(line)
            if not match:
                continue

            issue_type = match.group(4)
            old_name = match.group(5).strip()
            new_name = match.group(6).strip()
            sku = norm_sku(match.group(2))

            if issue_type == "None":
                issue_type = None
            if old_name == "None":
                old_name = None
            if new_name == "None":
                new_name = None

            found_by_action[sku] = ExtractionResult(
                page=int(match.group(1)),
                sku=sku,
                action=match.group(3),
                issue_type=issue_type,
                old_name=old_name,
                new_name=new_name,
            )

        all_results.extend(found_by_action.values())

    logger.info(f"Parsed {len(all_results)} total results from dry-run output")
    return all_results


def normalize_for_compare(name: str | None) -> str:
    """Normalize name for comparison."""
    if not name:
        return ""
    # Collapse whitespace, lowercase for fuzzy compare
    return re.sub(r"\s+", " ", name).strip().lower()


def compare_names(expected: str, actual: str | None) -> tuple[bool, str]:
    """Compare expected vs actual name."""
    if actual is None:
        return False, "missing"

    expected_norm = normalize_for_compare(expected)
    actual_norm = normalize_for_compare(actual)

    if expected_norm == actual_norm:
        return True, "exact_match"

    # Check if expected is substring of actual (partial match)
    if expected_norm in actual_norm:
        return False, f"actual_longer: '{actual}'"

    # Check if actual is substring of expected
    if actual_norm in expected_norm:
        return False, f"actual_shorter: '{actual}'"

    return False, f"mismatch: got '{actual}'"


def evaluate_case(
    page: int, case: RegressionCase, actual: ExtractionResult | None
) -> RegressionOutcome:
    """Evaluate a single case against actual extraction."""

    if actual is None:
        return RegressionOutcome(
            page=page,
            sku=case.sku,
            expected=case,
            actual=None,
            status="MISSING",
            detail="SKU not found in extraction output",
        )

    matches, detail = compare_names(case.expected_name, actual.new_name)

    # Determine outcome based on status and match
    if matches:
        if case.expected_status == "historical_db_damage_ignored":
            return RegressionOutcome(
                page=page,
                sku=case.sku,
                expected=case,
                actual=actual,
                status="UNCHANGED",
                detail="Matches (historical damage case)",
            )
        return RegressionOutcome(
            page=page,
            sku=case.sku,
            expected=case,
            actual=actual,
            status="UNCHANGED",
            detail="Matches expected",
        )

    # Doesn't match - determine if improvement or regression
    if case.expected_status == "historical_db_damage_ignored":
        # If we now get something better than expected (which was damaged), it's improvement
        # But we don't know what "good" looks like, so just mark as historical
        return RegressionOutcome(
            page=page,
            sku=case.sku,
            expected=case,
            actual=actual,
            status="HISTORICAL_ONLY",
            detail=f"DB damage case: {detail}",
        )

    if case.expected_status == "quality_debt_ignored":
        return RegressionOutcome(
            page=page,
            sku=case.sku,
            expected=case,
            actual=actual,
            status="UNCHANGED",
            detail=f"Quality debt (ignored): {detail}",
        )

    if case.expected_status == "legitimate_create":
        # For new products, we mainly care that extraction produces reasonable name
        # Some variance is acceptable
        return RegressionOutcome(
            page=page,
            sku=case.sku,
            expected=case,
            actual=actual,
            status="UNCHANGED",
            detail=f"New product: {detail}",
        )

    # must_pass or stable - these are regressions if they don't match
    if case.expected_status in ("must_pass", "stable"):
        # Check if it's actually better (unexpected improvement)
        # For target defects, if we get closer to expected, it's improvement
        if "TARGET DEFECT" in case.note and actual.new_name:
            # Simple heuristic: if actual contains expected SKU and reasonable text
            if case.sku in (actual.new_name or ""):
                # Check if it's closer to expected than a known bad pattern
                # Known bad: "420" appended for G3306
                known_bad_patterns = [" 420", " 34 ", " 34-44", " 122"]
                has_known_bad = any(
                    p in (actual.new_name or "") for p in known_bad_patterns
                )

                if not has_known_bad:
                    return RegressionOutcome(
                        page=page,
                        sku=case.sku,
                        expected=case,
                        actual=actual,
                        status="IMPROVED",
                        detail=f"Target defect improved: {detail}",
                    )

        return RegressionOutcome(
            page=page,
            sku=case.sku,
            expected=case,
            actual=actual,
            status="REGRESSED",
            detail=f"{case.expected_status} failed: {detail}",
        )

    # Unknown status - treat as potential defect
    return RegressionOutcome(
        page=page,
        sku=case.sku,
        expected=case,
        actual=actual,
        status="NEW_DEFECT",
        detail=f"Unexpected: {detail}",
    )


def run_regression(pdf_path: Path, brand: str, pages: list[int]) -> RegressionReport:
    """Run full regression evaluation."""

    baseline = load_baseline()
    actual_results = run_dry_run_import(pdf_path, brand, pages) or []

    # Index actual results by (page, sku)
    actual_by_key: dict[tuple[int, str], ExtractionResult] = {}
    for r in actual_results:
        actual_by_key[(r.page, norm_sku(r.sku))] = r

    report = RegressionReport()

    for page in pages:
        cases = baseline.get(page, [])
        for case in cases:
            key = (page, norm_sku(case.sku))
            actual = actual_by_key.get(key)
            outcome = evaluate_case(page, case, actual)

            if outcome.status == "IMPROVED":
                report.improved.append(outcome)
            elif outcome.status == "UNCHANGED":
                report.unchanged.append(outcome)
            elif outcome.status == "REGRESSED":
                report.regressed.append(outcome)
            elif outcome.status == "HISTORICAL_ONLY":
                report.historical_only.append(outcome)
            elif outcome.status == "NEW_DEFECT":
                report.new_defects.append(outcome)
            else:
                report.missing.append(outcome)

    return report


def print_report(report: RegressionReport) -> None:
    """Print human-readable regression report."""

    print("\n" + "=" * 70)
    print("SANTEH REGRESSION VERDICT")
    print("=" * 70)

    # IMPROVED
    print("\nIMPROVED")
    if report.improved:
        for o in report.improved:
            print(f"  page={o.page} sku={o.sku}")
            print(f"    expected: {o.expected.expected_name}")
            print(f"    actual:   {o.actual.new_name if o.actual else 'N/A'}")
            print(f"    detail:   {o.detail}")
    else:
        print("  (none)")

    # UNCHANGED
    print("\nUNCHANGED")
    if report.unchanged:
        for o in report.unchanged:
            status_marker = f"[{o.expected.expected_status}]"
            print(f"  page={o.page} sku={o.sku} {status_marker}")
    else:
        print("  (none)")

    # REGRESSED
    print("\nREGRESSED")
    if report.regressed:
        for o in report.regressed:
            print(f"  ⚠️  page={o.page} sku={o.sku} [{o.expected.expected_status}]")
            print(f"      expected: {o.expected.expected_name}")
            print(f"      actual:   {o.actual.new_name if o.actual else 'N/A'}")
            print(f"      detail:   {o.detail}")
    else:
        print("  (none)")

    # HISTORICAL_DB_DAMAGE ONLY
    print("\nHISTORICAL_DB_DAMAGE ONLY")
    if report.historical_only:
        for o in report.historical_only:
            print(f"  page={o.page} sku={o.sku}")
            print(f"    note: {o.expected.note[:60]}...")
    else:
        print("  (none)")

    # NEW CURRENT EXTRACTION DEFECTS
    print("\nNEW CURRENT EXTRACTION DEFECTS")
    if report.new_defects:
        for o in report.new_defects:
            print(f"  🐛 page={o.page} sku={o.sku}")
            print(f"      expected: {o.expected.expected_name}")
            print(f"      actual:   {o.actual.new_name if o.actual else 'N/A'}")
            print(f"      detail:   {o.detail}")
    else:
        print("  (none)")

    # MISSING
    if report.missing:
        print("\nMISSING (not found in extraction)")
        for o in report.missing:
            print(f"  page={o.page} sku={o.sku}")

    # FINAL VERDICT
    print("\n" + "=" * 70)

    # Determine pass/fail
    fail_reasons = []

    must_pass_regressed = [
        r for r in report.regressed if r.expected.expected_status == "must_pass"
    ]
    stable_regressed = [
        r for r in report.regressed if r.expected.expected_status == "stable"
    ]
    must_pass_missing = [
        r for r in report.missing if r.expected.expected_status == "must_pass"
    ]
    stable_missing = [
        r for r in report.missing if r.expected.expected_status == "stable"
    ]

    if must_pass_regressed:
        fail_reasons.append(f"{len(must_pass_regressed)} must_pass case(s) regressed")
    if stable_regressed:
        fail_reasons.append(f"{len(stable_regressed)} stable case(s) regressed")
    if must_pass_missing:
        fail_reasons.append(f"{len(must_pass_missing)} must_pass case(s) missing")
    if stable_missing:
        fail_reasons.append(f"{len(stable_missing)} stable case(s) missing")
    if report.new_defects:
        fail_reasons.append(f"{len(report.new_defects)} new extraction defect(s)")

    if fail_reasons:
        verdict = "FAIL"
        verdict_detail = "; ".join(fail_reasons)
    else:
        verdict = "PASS"
        improvements = len(report.improved)
        if improvements > 0:
            verdict_detail = f"{improvements} target defect(s) improved"
        else:
            verdict_detail = "no regressions, no improvements"

    print(f"FINAL VERDICT: {verdict}")
    print(f"  {verdict_detail}")
    print("=" * 70 + "\n")

    # Exit code
    sys.exit(0 if verdict == "PASS" else 1)


def main():
    parser = argparse.ArgumentParser(
        description="Santeh PDF Extraction Regression Harness",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full regression set
  python tools/run_santeh_regression.py --pdf "2026 GAPPOсмесители каталог .pdf" --brand GAPPO
  
  # Specific pages
  python tools/run_santeh_regression.py --pdf "catalog.pdf" --brand GAPPO --pages 123,138
  
  # Profile (predefined page set)
  python tools/run_santeh_regression.py --pdf "catalog.pdf" --brand GAPPO --profile santeh-core
""",
    )

    parser.add_argument("--pdf", "-p", required=True, help="Path to PDF file")
    parser.add_argument("--brand", "-b", default="GAPPO", help="Brand hint")
    parser.add_argument(
        "--pages",
        help='Comma-separated pages (e.g., "91,97,123") or omit for profile',
    )
    parser.add_argument(
        "--profile",
        choices=["santeh-core"],
        default="santeh-core",
        help="Use predefined page set",
    )

    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"ERROR: PDF not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    # Determine pages
    if args.pages:
        pages = [int(p.strip()) for p in args.pages.split(",")]
    else:
        pages = PROFILES.get(args.profile, PROFILES["santeh-core"])

    print(f"Running regression on pages: {pages}")

    report = run_regression(pdf_path, args.brand, pages)
    print_report(report)


if __name__ == "__main__":
    main()
