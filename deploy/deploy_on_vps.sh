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
docker compose -f "$COMPOSE_FILE" run --rm migrate
docker compose -f "$COMPOSE_FILE" up -d --remove-orphans
docker compose -f "$COMPOSE_FILE" ps

echo "Deploy complete."
