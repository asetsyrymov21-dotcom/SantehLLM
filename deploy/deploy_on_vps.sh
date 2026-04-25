#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/santeh}"
BRANCH="${BRANCH:-main}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.vps.yml}"

cd "$APP_DIR"

echo "Deploying Santeh from branch: $BRANCH"

git fetch origin "$BRANCH"
git reset --hard "origin/$BRANCH"

if [ ! -f ".env" ]; then
  echo "ERROR: .env is missing on VPS at $APP_DIR/.env"
  echo "Create it from .env.example and add production secrets."
  exit 1
fi

docker compose -f "$COMPOSE_FILE" build
docker compose -f "$COMPOSE_FILE" up -d db
docker compose -f "$COMPOSE_FILE" exec -T db sh -c \
  'until pg_isready -U "${POSTGRES_USER:-postgres}" >/dev/null 2>&1; do sleep 1; done'
docker compose -f "$COMPOSE_FILE" exec -T db sh -c \
  'createdb -U "${POSTGRES_USER:-postgres}" "${POSTGRES_DB:-santeh}" 2>/dev/null || true'
docker compose -f "$COMPOSE_FILE" run --rm migrate
docker compose -f "$COMPOSE_FILE" up -d --remove-orphans
docker compose -f "$COMPOSE_FILE" ps

echo "Deploy complete."
