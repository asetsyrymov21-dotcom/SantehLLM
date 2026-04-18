# Stock Import Implementation

Безопасный импорт остатков для FRAP с dry-run по умолчанию.

## Архитектура

### Новые модули

```
app/utils/sku_utils.py                    # Централизованная нормализация SKU + derive brand
app/utils/stock_parser.py                 # Парсер значений остатков (10+, 5-10, etc.)
app/services/stock_import/excel_parser.py # Парсинг Excel
app/services/stock_import/matcher.py      # Мэтчинг с отчётом
app/services/stock_import/importer.py     # Коммит логика
app/services/stock_import/__init__.py     # Экспорты
```

### Скрипты

```
scripts/backfill_brand_from_sku.py        # Backfill брендов
scripts/import_frap_stock.py              # CLI для импорта остатков
```

## Использование

### 1. Backfill брендов (из SKU)

```bash
# Dry-run (по умолчанию)
python scripts/backfill_brand_from_sku.py --dry-run

# Показать первые 10
python scripts/backfill_brand_from_sku.py --dry-run --limit 10

# Применить изменения
python scripts/backfill_brand_from_sku.py --commit
```

**Логика:**
- F* -> FRAP
- G* -> GAPPO
- Иначе None

**Отчёт:**
- Total products checked
- Products with recognizable prefix
- Brand fixes planned
- Skipped (already correct)
- Conflicts (current brand != derived)

### 2. Импорт остатков FRAP

```bash
# Dry-run (по умолчанию)
python scripts/import_frap_stock.py --file "остатки.xlsx" --dry-run

# Применить изменения
python scripts/import_frap_stock.py --file "остатки.xlsx" --commit

# Обработать дубликаты (по умолчанию пропускаются)
python scripts/import_frap_stock.py --file "остатки.xlsx" --commit --include-duplicates
```

**Безопасность:**
- Только dry-run по умолчанию
- Только обновление inventory (stock_doc)
- Никаких созданий продуктов
- Никаких изменений name/description/brand/category

**Фильтрация:**
- Только SKU начинающиеся с F (FRAP)
- GAPPO SKU пропускаются
- Exact match по normalized SKU

**Парсинг количества:**
- "12" -> exact=12
- "10+" -> range_plus, min=10
- "5-10" -> range_dash, min=5
- "", "N/A" -> empty

## Правила SKU

### Нормализация (app/utils/sku_utils.py)

```python
from app.utils.sku_utils import normalize_sku, derive_brand_from_sku

# Нормализация
normalize_sku("  f1002-b  ")      # "F1002-B"
normalize_sku("арт. F1002")        # "F1002"
normalize_sku("F1002–B")           # "F1002-B" (en-dash -> hyphen)

# Brand derivation
derive_brand_from_sku("F1002")    # "FRAP"
derive_brand_from_sku("G1234")    # "GAPPO"
derive_brand_from_sku("X1234")    # None
```

### Доступные функции

- `normalize_sku()` - нормализация SKU
- `derive_brand_from_sku()` - определение бренда
- `is_frap_sku()` / `is_gappo_sku()` - проверки
- `get_brand_from_normalized_sku()` - быстрый lookup

## Тесты

```bash
# Тесты SKU utilities
python -m pytest tests/test_sku_utils.py -v

# Тесты stock parser
python -c "from app.utils.stock_parser import parse_stock_value; print(parse_stock_value('10+'))"

# Тесты stock import
python -m pytest tests/test_stock_import.py -v
```

## Примеры отчётов

### Dry-run output (остатки)

```
============================================================
FRAP STOCK IMPORT DRY RUN
============================================================
Source file: остатки.xlsx
Total rows scanned: 500
Non-empty rows: 450
Rows with article: 445
FRAP candidate rows: 320
Valid normalized SKU: 318
Duplicate SKU in source: 5
Matched in DB: 310
Unmatched in DB: 8
Invalid/empty qty: 12
Skipped non-FRAP: 130
Planned updates: 310
============================================================
```

### Detailed report

```
--- DETAILED REPORT ---
Row   SKU Raw         SKU Norm     Qty Raw    Qty Parsed Product ID Status          Notes
------------------------------------------------------------------------------------------------------------------------
1     F1002           F1002        10         10         123        matched
2     F1003           F1003        10+        10+        124        matched
3     F9999           F9999        5          5          -          unmatched         Product not found in database
4     G1001           G1001        20         20         -          skipped_non_frap  Brand 'GAPPO' != filter 'FRAP'
```

## Интеграция с существующим кодом

### Использование в импортерах

Старые модули автоматически используют новый `normalize_sku`:
- `app/services/product_import/normalizer.py`
- `app/services/product_import/excel_normalizer.py`

### Добавление brand в импорт

```python
from app.utils.sku_utils import derive_brand_from_sku

# В коде импорта
normalized_sku = normalize_sku(raw_sku)
brand = derive_brand_from_sku(normalized_sku)
```

## Ограничения и безопасность

1. **Dry-run по умолчанию** - никаких изменений без `--commit`
2. **Дубликаты** - по умолчанию пропускаются (до определения merge policy)
3. **Только FRAP** - GAPPO SKU игнорируются в этом импортере
4. **Только существующие** - новые продукты не создаются
5. **Только stock** - name/description/brand не меняются

## Планы развития

1. GAPPO stock import (аналогичный модуль)
2. Merge policy для дубликатов (sum/max/last)
3. Интеграция с stock_movements для audit trail
4. Web UI для просмотра отчётов