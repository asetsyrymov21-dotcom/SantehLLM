from functools import lru_cache

from pydantic import BaseModel, Field
import os


class Settings(BaseModel):
    """Application configuration loaded from environment variables."""

    app_name: str = Field(default="Santeh Inventory")
    debug: bool = Field(default=False)
    api_v1_prefix: str = Field(default="/api/v1")

    database_url: str = Field(default="")

    telegram_bot_token: str = Field(default="CHANGE_ME")
    telegram_parse_mode: str = Field(default="HTML")

    openai_api_key: str = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_chat_model: str = Field(default_factory=lambda: os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini"))
    gappo_indexes_path: str = Field(default_factory=lambda: os.getenv("GAPPO_INDEXES_PATH", "indexes.json"))

    @classmethod
    def load(cls) -> "Settings":
        return cls(
            app_name=os.getenv("APP_NAME", cls.model_fields["app_name"].default),
            debug=os.getenv("DEBUG", str(cls.model_fields["debug"].default)).lower() == "true",
            api_v1_prefix=os.getenv("API_V1_PREFIX", cls.model_fields["api_v1_prefix"].default),
            database_url=os.getenv("DATABASE_URL", cls.model_fields["database_url"].default),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", cls.model_fields["telegram_bot_token"].default),
            telegram_parse_mode=os.getenv("TELEGRAM_PARSE_MODE", cls.model_fields["telegram_parse_mode"].default),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            openai_chat_model=os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
            gappo_indexes_path=os.getenv("GAPPO_INDEXES_PATH", "indexes.json"),
        )


@lru_cache
def get_settings() -> Settings:
    return Settings.load()


settings = get_settings()
