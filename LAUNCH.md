# Santeh Launch Runbook

## Current ingestion path
- Source: Excel
- Main script: `scripts/import_excel_products.py`
- Working file: `2026 прайс ОПТ .xlsx`
- Header row: `2`

## Current policy
- Empty or weak title rows are NOT skipped
- They are saved as-is
- They get `needs_pdf_enrichment=true`

## Confirmed current status
- total products built: 1243
- updated: 1243
- failed: 0

## Known root causes
- `title_empty_in_excel` = bad source Excel
- `weak_title_after_normalize` = grouped rows / short labels / variants

## Do not do now
- No PDF pipeline work
- No grouped-row intelligence
- No big refactor
- No Excel cleanup project

## Important env notes

- Postgres DB name must be `santeh`, not `postgres`
- For local API checks use: `http://localhost:8000/api/v1`
- For bot inside Docker use: `http://api:8000/api/v1`

## Canonical import command
```bash
python scripts/import_excel_products.py "2026 прайс ОПТ .xlsx" --header-row 2