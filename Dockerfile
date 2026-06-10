FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

RUN addgroup --system app && adduser --system --ingroup app app

COPY app ./app
COPY scripts ./scripts
COPY alembic ./alembic
COPY alembic.ini ./
COPY .env.example ./.env.example
COPY rag_chunks.jsonl products.json indexes.json ./

RUN mkdir -p /app/storage/generated_documents /app/reports \
    && chown -R app:app /app/storage /app/reports

ENV PYTHONPATH=/app

USER app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
