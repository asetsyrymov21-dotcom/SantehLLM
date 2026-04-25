# PROJECT MAP — Santeh Inventory

> Карта проекта для быстрой навигации агента. Перед редактированием любого файла — смотри сюда, не сканируй весь проект.

---

## Точка входа

| Файл | Назначение |
|------|-----------|
| `app/main.py` | FastAPI app factory — создаёт приложение, подключает роутеры |
| `app/bot/main.py` | Точка запуска Telegram-бота (aiogram polling) |
| `docker-compose.yml` | Запуск всего стека: API + бот + PostgreSQL |
| `Dockerfile` | Образ приложения |
| `.env` / `.env.example` | Переменные окружения (токены, DB URL, OpenAI key) |

---

## Конфигурация

| Файл | Назначение |
|------|-----------|
| `app/core/config.py` | Pydantic Settings — все env-переменные приложения |
| `app/core/logging.py` | Настройка логирования |
| `app/bot/config.py` | Конфиг бота (BOT_TOKEN и т.п.) |
| `alembic.ini` | Конфиг Alembic (миграции БД) |

---

## База данных

| Файл | Назначение |
|------|-----------|
| `app/db/models.py` | **Главный файл моделей** — все SQLAlchemy ORM-модели: `Product`, `Inventory`, `StockMovement`, `Sale`, `SaleItem`, `Document`, `User` + enums |
| `app/db/rag_models.py` | Модели для RAG-системы (эмбеддинги, чанки) |
| `app/db/base.py` | Базовый класс `Base` для всех моделей |
| `app/db/mixins.py` | Миксины `TimestampMixin`, `CreatedAtMixin` |
| `app/db/session.py` | Сессия PostgreSQL (async SQLAlchemy) |
| `app/db/session_sqlite.py` | Сессия SQLite (для тестов/локальной разработки) |

### Миграции

| Файл | Назначение |
|------|-----------|
| `alembic/env.py` | Окружение Alembic |
| `alembic/versions/202603291810_initial.py` | Начальная миграция |
| `alembic/versions/202603292230_add_rag_tables.py` | Добавление RAG-таблиц |
| `alembic/versions/202603301200_update_source_type.py` | Обновление enum source_type |
| `alembic/versions/202603301300_add_cancelled_status.py` | Добавление статуса CANCELLED |

---

## API (FastAPI)

| Файл | Назначение |
|------|-----------|
| `app/api/routes.py` | Главный роутер — собирает все под-роутеры |
| `app/api/deps.py` | Dependency Injection (получение сессии БД) |
| `app/api/products.py` | CRUD эндпоинты для товаров |
| `app/api/inventory.py` | Эндпоинты остатков/склада |
| `app/api/sales.py` | Эндпоинты продаж |
| `app/api/search.py` | Поиск товаров по тексту |
| `app/api/imports.py` | Импорт товаров/прайсов (Excel, PDF) |
| `app/api/documents.py` | Генерация документов (накладные и т.п.) |
| `app/api/rag.py` | Эндпоинты RAG-поиска |
| `app/api/health.py` | Health-check `/health` |

---

## Telegram-бот (aiogram)

| Файл | Назначение |
|------|-----------|
| `app/bot/handlers/__init__.py` | Регистрация всех хендлеров |
| `app/bot/handlers/start.py` | `/start`, приветствие |
| `app/bot/handlers/product.py` | Просмотр карточки товара |
| `app/bot/handlers/search.py` | Поиск товара через бот |
| `app/bot/handlers/sale.py` | Создание продажи через бот |
| `app/bot/handlers/navigation.py` | Навигация по меню |
| `app/bot/handlers/batch_sku.py` | Пакетный ввод SKU |
| `app/bot/handlers/excel_request.py` | Запрос/выгрузка Excel-отчётов |
| `app/bot/handlers/stock_import.py` | Импорт остатков через бот |
| `app/bot/handlers/voice.py` | Голосовые сообщения (STT) |
| `app/bot/keyboards.py` | Все inline/reply клавиатуры |
| `app/bot/states.py` | FSM-состояния (aiogram) |
| `app/bot/storage.py` | Хранилище состояний |
| `app/bot/api_client.py` | HTTP-клиент бота → FastAPI |
| `app/bot/stt/base.py` | Базовый класс Speech-to-Text |
| `app/bot/stt/stub.py` | Заглушка STT (для тестов) |

---

## Сервисы (бизнес-логика)

| Файл | Назначение |
|------|-----------|
| `app/services/product.py` | Бизнес-логика товаров |
| `app/services/inventory.py` | Логика остатков/движений |
| `app/services/sales.py` | Логика продаж |
| `app/services/search.py` | Текстовый поиск по товарам |
| `app/services/imports.py` | Оркестратор импорта |
| `app/services/import_service.py` | Сервис импорта (альтернативный entry) |
| `app/services/document.py` | Генерация документов |
| `app/services/rag.py` | RAG-сервис (поиск по эмбеддингам) |

### Импорт товаров из Excel

| Файл | Назначение |
|------|-----------|
| `app/services/product_import/importer.py` | Главный оркестратор импорта товаров |
| `app/services/product_import/excel_loader.py` | Загрузка и парсинг Excel-файла |
| `app/services/product_import/excel_mapper.py` | Маппинг колонок Excel → поля модели |
| `app/services/product_import/excel_normalizer.py` | Нормализация данных из Excel |
| `app/services/product_import/normalizer.py` | Нормализация имён/брендов |
| `app/services/product_import/dedup.py` | Дедупликация товаров |
| `app/services/product_import/merge_service.py` | Слияние дублей |
| `app/services/product_import/merge_rules.py` | Правила слияния |
| `app/services/product_import/finalize_service.py` | Финализация и сохранение |
| `app/services/product_import/product_persistence_service.py` | Персистентность (запись в БД) |
| `app/services/product_import/brand_overrides_service.py` | Ручные переопределения брендов |
| `app/services/product_import/stock_import_service.py` | Импорт остатков (количество) |

### Импорт остатков

| Файл | Назначение |
|------|-----------|
| `app/services/stock_import/importer.py` | Оркестратор импорта остатков |
| `app/services/stock_import/excel_parser.py` | Парсинг Excel с остатками |
| `app/services/stock_import/matcher.py` | Сопоставление SKU (v1) |
| `app/services/stock_import/matcher_v2.py` | Сопоставление SKU (v2, улучшенный) |
| `app/services/stock_import/unmatched_analyzer.py` | Анализ несопоставленных SKU |
| `app/services/stock_import/test_output.py` | Отладочный вывод результатов |

### Парсинг PDF (каталог товаров)

| Файл | Назначение |
|------|-----------|
| `app/services/pdf/extractor.py` | **Главный экстрактор** — точка входа PDF-пайплайна |
| `app/services/pdf/router.py` | Маршрутизация по типу страницы |
| `app/services/pdf/classifier.py` | Классификация страниц PDF |
| `app/services/pdf/product_cards.py` | Извлечение карточек товаров |
| `app/services/pdf/product_cards_legacy.py` | Старая логика карточек |
| `app/services/pdf/product_cards_type_columns.py` | Карточки-колонки |
| `app/services/pdf/product_cards_type_grid.py` | Карточки-сетка |
| `app/services/pdf/product_cards_type_single.py` | Одиночные карточки |
| `app/services/pdf/card_boundaries.py` | Определение границ карточек |
| `app/services/pdf/variant_extractor.py` | Извлечение вариантов товара |
| `app/services/pdf/mapper.py` | Маппинг извлечённых данных → модели |
| `app/services/pdf/normalizer.py` | Нормализация PDF-данных |
| `app/services/pdf/sku_utils.py` | Утилиты для SKU из PDF |
| `app/services/pdf/shared_patterns.py` | Общие regex-паттерны |
| `app/services/pdf/page_features.py` | Признаки страницы для классификатора |
| `app/services/pdf/page_types.py` | Типы страниц PDF |
| `app/services/pdf/title_candidates.py` | Кандидаты на заголовок серии |
| `app/services/pdf/title_filters.py` | Фильтрация заголовков |
| `app/services/pdf/series_title.py` | Определение серии товара |
| `app/services/pdf/nearby_page_title.py` | Заголовок с соседних страниц |
| `app/services/pdf/attribute_context.py` | Контекст атрибутов |
| `app/services/pdf/extraction_types.py` | Типы данных извлечения |
| `app/services/pdf/product_card_quality.py` | Оценка качества карточки |
| `app/services/pdf/inspector.py` | Инспектор страниц (отладка) |
| `app/services/pdf/debug_helpers.py` | Хелперы отладки PDF |
| `app/services/pdf/docling/extractor.py` | Docling-экстрактор (альтернативный) |
| `app/services/pdf/docling/classifier.py` | Docling-классификатор |
| `app/services/pdf/docling/models.py` | Модели данных Docling |

### PDF Enrichment (обогащение товаров из PDF)

| Файл | Назначение |
|------|-----------|
| `app/services/pdf_enrichment/service.py` | **Главный сервис обогащения** |
| `app/services/pdf_enrichment/extractor.py` | Извлечение данных для обогащения |
| `app/services/pdf_enrichment/matcher.py` | Сопоставление товара с PDF |
| `app/services/pdf_enrichment/decision.py` | Логика принятия решения об обновлении |
| `app/services/pdf_enrichment/fast_indexer.py` | Быстрый индекс для поиска в PDF |
| `app/services/pdf_enrichment/repository.py` | Работа с БД для enrichment |
| `app/services/pdf_enrichment/models.py` | Pydantic-модели enrichment |
| `app/services/pdf_enrichment/bootstrap.py` | Инициализация сервиса |

### Проверка запросов покупателей

| Файл | Назначение |
|------|-----------|
| `app/services/request_check/checker.py` | Главный чекер запросов |
| `app/services/request_check/parser.py` | Парсинг текстового запроса |
| `app/services/request_check/excel_parser.py` | Парсинг Excel-запросов |
| `app/services/request_check/excel_report.py` | Excel-отчёт по результатам проверки |
| `app/services/request_check/formatter.py` | Форматирование ответа |
| `app/services/request_check/batch_sku.py` | Пакетная проверка по SKU |
| `app/services/request_check/schemas.py` | Схемы данных проверки |

### Post-import

| Файл | Назначение |
|------|-----------|
| `app/services/post_import/reporting_service.py` | Отчёт после импорта |

---

## Репозитории (слой доступа к БД)

| Файл | Назначение |
|------|-----------|
| `app/repositories/product.py` | CRUD для `Product` |
| `app/repositories/inventory.py` | CRUD для `Inventory` / `StockMovement` |
| `app/repositories/sale.py` | CRUD для `Sale` / `SaleItem` |
| `app/repositories/document.py` | CRUD для `Document` |
| `app/repositories/rag_repository.py` | Репозиторий RAG-данных |

---

## Схемы Pydantic (request/response)

| Файл | Назначение |
|------|-----------|
| `app/schemas/product.py` | Схемы товара (Create, Update, Read) |
| `app/schemas/inventory.py` | Схемы остатков |
| `app/schemas/sale.py` | Схемы продаж |
| `app/schemas/excel_row.py` | Схема строки Excel при импорте |
| `app/schemas/product_extraction.py` | Схема извлечённого из PDF товара |
| `app/schemas/product_merge.py` | Схема результата слияния |
| `app/schemas/utility.py` | Вспомогательные схемы |

---

## RAG (поиск по эмбеддингам)

| Файл | Назначение |
|------|-----------|
| `app/rag/rag_pipeline.py` | Главный RAG-пайплайн |
| `app/rag/embeddings.py` | Генерация эмбеддингов |
| `app/rag/retrieval.py` | Retrieval (поиск ближайших) |
| `app/rag/rerank.py` | Реранкинг результатов |
| `app/rag/db.py` | БД-операции для RAG |
| `app/rag/app/rag/embeddings.py` | Эмбеддинги (вложенный модуль) |
| `app/rag/app/rag/indexer.py` | Индексатор документов |
| `app/rag/app/rag/retrieval_products.py` | Retrieval для товаров |
| `app/rag/app/rag/retrieval_documents.py` | Retrieval для документов |
| `app/rag/app/rag/rerank.py` | Реранкинг (вложенный модуль) |
| `app/rag/app/rag/schemas.py` | Схемы RAG |
| `app/rag/app/services/search_service.py` | Сервис поиска |
| `app/rag/app/api/search.py` | API-эндпоинт поиска (вложенный) |
| `app/rag/scripts/search_cli.py` | CLI-утилита поиска |
| `app/rag/migrations/versions/20260329_product_embeddings.py` | Миграция таблицы эмбеддингов |

---

## Утилиты

| Файл | Назначение |
|------|-----------|
| `app/utils/llm.py` | Вызовы OpenAI (chat completion, extraction) |
| `app/utils/embeddings.py` | Утилиты эмбеддингов |
| `app/utils/excel.py` | Чтение/запись Excel (openpyxl/pandas) |
| `app/utils/pdf_parser.py` | Базовый парсер PDF (pdfplumber) |
| `app/utils/sku_utils.py` | Нормализация и парсинг SKU |
| `app/utils/stock_parser.py` | Парсинг данных остатков |
| `app/utils/chunk.py` | Разбивка текста на чанки (для RAG) |

---

## Скрипты (разовые/административные)

| Файл | Назначение |
|------|-----------|
| `import_pdfs.py` | Запуск импорта PDF в корне проекта |
| `scripts/import_excel_products.py` | Импорт товаров из Excel |
| `scripts/import_excel_stock.py` | Импорт остатков из Excel |
| `scripts/import_frap_stock.py` | Импорт остатков FRAP (v1) |
| `scripts/import_frap_stock_v2.py` | Импорт остатков FRAP (v2) |
| `scripts/import_missing_products.py` | Импорт недостающих товаров |
| `scripts/import_extracted_products.py` | Импорт извлечённых из PDF товаров |
| `scripts/apply_brand_overrides.py` | Применение ручных переопределений бренда |
| `scripts/backfill_brand_from_sku.py` | Восстановление бренда из SKU |
| `scripts/fix_product_brands.py` | Исправление брендов |
| `scripts/cleanup_bad_product_names.py` | Чистка плохих названий |
| `scripts/manual_fix_product_names.py` | Ручное исправление названий |
| `scripts/audit_products.py` | Аудит товаров |
| `scripts/audit_missing_products.py` | Аудит отсутствующих товаров |
| `scripts/audit_unmatched_skus.py` | Аудит несопоставленных SKU |
| `scripts/analyze_unmatched_skus.py` | Анализ несопоставленных SKU |
| `scripts/run_stock_import.py` | Запуск импорта остатков |
| `scripts/run_pdf_enrichment_flagged.py` | Запуск обогащения по флагам |
| `scripts/build_pdf_text_dump.py` | Дамп текста из PDF |
| `scripts/prepare_missing_products_import.py` | Подготовка списка недостающих |
| `scripts/export_damaged_product_names.py` | Экспорт повреждённых названий |
| `scripts/find_suspicious_product_names.py` | Поиск подозрительных названий |
| `scripts/review_suspicious_gappo_names.py` | Ревью подозрительных названий GAPPO |
| `scripts/inspect_damaged_name_sources.py` | Инспекция источников повреждений |
| `scripts/inspect_rag_chunks_for_damaged_names.py` | Инспекция RAG-чанков |
| `scripts/inspect_schema_candidates.py` | Инспекция кандидатов схемы |
| `scripts/test_pdf_extract.py` | Тест PDF-экстрактора |
| `scripts/test_page_extraction.py` | Тест извлечения страниц |
| `scripts/test_extraction_audit.py` | Аудит результатов извлечения |
| `scripts/test_docling_poc.py` | PoC тест Docling |

---

## Тесты

| Файл | Назначение |
|------|-----------|
| `tests/test_excel_pipeline_regression.py` | Регрессия Excel-пайплайна |
| `tests/test_excel_stock_import.py` | Тест импорта остатков из Excel |
| `tests/test_sku_first_import.py` | Тест первичного импорта SKU |
| `tests/test_sku_utils.py` | Тест утилит SKU |
| `tests/test_stock_import.py` | Тест импорта остатков |
| `tests/test_stock_matcher_fallbacks.py` | Тест фолбэков матчера |
| `tests/test_stock_parser_qty.py` | Тест парсинга количества |
| `tests/test_unmatched_analyzer.py` | Тест анализатора несопоставленных |
| `tests/regression/santeh_expected_titles.json` | Ожидаемые заголовки для регрессии |
| `app/rag/tests/test_search_smoke.py` | Дымовой тест RAG-поиска |
| `tools/run_santeh_regression.py` | Запуск регрессионного набора |

---

## Данные / шаблоны

| Файл | Назначение |
|------|-----------|
| `app/documents/templates/invoice_template.xlsx` | Шаблон накладной Excel |
| `storage/pdf_cache/*.json` | Кэш распарсенных страниц PDF (GAPPO 2026) |
| `2026 GAPPOсмесители каталог .pdf` | Исходный PDF-каталог GAPPO 2026 |
| `2026 прайс ОПТ .xlsx` | Оптовый прайс 2026 |
| `Ostatki.xlsx` | Файл остатков |
| `Прайс Инженерка ОПТ 02.26.xlsx` | Прайс инженерки февраль 2026 |

---

## Документация

| Файл | Назначение |
|------|-----------|
| `LAUNCH.md` | Инструкция по запуску проекта |
| `STOCK_IMPORT_README.md` | Инструкция по импорту остатков |
| `docs/BRAND_OVERRIDES_INTEGRATION.md` | Интеграция переопределений брендов |
