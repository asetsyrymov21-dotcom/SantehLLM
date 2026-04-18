# Интеграция Brand Overrides с ProductImporter

## Обзор

Система brand overrides автоматически применяет бренды из таблицы `product_brand_overrides` после каждого импорта.

**Ключевое требование**: После применения overrides ни один продукт не должен иметь NULL brand. Если такие продукты остаются — pipeline падает с ошибкой.

## Быстрая интеграция

### Вариант 1: Ручной вызов после импорта (рекомендуется для начала)

```python
from app.services.product_import import ProductImporter, finalize_import
from app.db.session import SessionLocal

session = SessionLocal()
try:
    importer = ProductImporter(session)
    result = importer.import_products(items, dry_run=False)
    
    # После успешного импорта применяем brand overrides
    finalize_import(session, dry_run=False)
    
    session.commit()
    print(f"Import complete: {result.created} created, {result.updated} updated")
except Exception as e:
    session.rollback()
    raise
finally:
    session.close()
```

### Вариант 2: Интеграция в ProductImporter.import_products()

Добавьте в конец метода `import_products()` (после `logger.info("Import committed to database")`):

```python
# Step 4: Apply brand overrides after successful commit
from .finalize_service import finalize_import
try:
    finalize_import(self.session, dry_run=dry_run)
except BrandOverridesAuditError as e:
    logger.error(f"[IMPORT] Brand overrides audit failed: {e}")
    # Pipeline fails - need to fix product_brand_overrides table
    raise
```

## Ручное управление

### Проверка перед коммитом (dry-run)

```bash
python scripts/apply_brand_overrides.py --dry-run
```

Вывод:
```
DRY RUN MODE - checking what would be changed...
Would update: 15 rows
NULL brands after: 0
AUDIT PASSED: No NULL brands after overrides
```

### Применение вручную

```bash
python scripts/apply_brand_overrides.py --commit
```

## Если audit падает

### Сценарий: NULL brands после overrides

```
[IMPORT] Brand overrides audit failed: Invariant violation: 3 products still have NULL brand after overrides
```

**Решение**:

1. Найдите продукты без brand:
```sql
SELECT p.id, p.sku, p.name 
FROM products p 
WHERE p.brand IS NULL 
  AND EXISTS (
    SELECT 1 FROM product_brand_overrides bo 
    WHERE bo.sku = p.sku
  );
```

2. Добавьте недостающие SKU в таблицу overrides:
```sql
INSERT INTO product_brand_overrides (sku, brand, priority, source, notes)
VALUES ('MISSING-SKU-1', 'CorrectBrand', 100, 'manual_fix', 'Added after audit failure');
```

3. Перезапустите импорт или примените overrides вручную.

## API Reference

### BrandOverridesService

```python
from app.services.product_import import BrandOverridesService

service = BrandOverridesService(session)

# Проверить что будет изменено (без записи в БД)
result = service.apply_overrides_silent()
print(f"Rows to update: {result.updated_rows}")
print(f"NULL brands after: {result.total_brand_null}")

# Применить с аудитом (падает если остались NULL)
result = service.apply_overrides()  # Raises BrandOverridesAuditError on failure
```

### Исключения

```python
from app.services.product_import import BrandOverridesAuditError

try:
    service.apply_overrides()
except BrandOverridesAuditError as e:
    print(f"Failed after updating {e.updated_rows} rows")
    print(f"Products with NULL brand: {e.null_count}")
    print(f"Sample NULL brand SKUs: {e.null_brand_skus}")
```

## Тестирование

### Юнит-тест

```python
def test_brand_overrides_audit():
    """Ensure pipeline fails if NULL brands remain after overrides."""
    from app.services.product_import import BrandOverridesAuditError
    
    session = create_test_session()
    
    # Create product without brand and no override
    product = create_product(session, sku="TEST-001", brand=None)
    session.commit()
    
    # Should raise audit error
    with pytest.raises(BrandOverridesAuditError) as exc_info:
        finalize_import(session, dry_run=False)
    
    assert "3 products still have NULL brand" in str(exc_info.value)
```

## Миграция существующих данных

```sql
-- Найти все SKU без brand
SELECT DISTINCT p.sku 
FROM products p 
WHERE p.brand IS NULL;

-- Добавить их в overrides с правильными брендами
INSERT INTO product_brand_overrides (sku, brand, priority, source)
SELECT DISTINCT p.sku, 'UnknownBrand', 50, 'migration'
FROM products p 
WHERE p.brand IS NULL;
```

Затем запустите:
```bash
python scripts/apply_brand_overrides.py --commit
```