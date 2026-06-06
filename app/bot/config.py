from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_API_BASE_URL = os.getenv("TELEGRAM_API_BASE_URL", "").rstrip("/")
TELEGRAM_MAX_DOWNLOAD_MB = int(os.getenv("TELEGRAM_MAX_DOWNLOAD_MB", "20"))
TELEGRAM_ADMIN_IDS = {
    int(value.strip())
    for value in os.getenv("TELEGRAM_ADMIN_IDS", "").split(",")
    if value.strip().isdigit()
}

if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")


def is_admin_user(user_id: int | None) -> bool:
    return user_id is not None and user_id in TELEGRAM_ADMIN_IDS
