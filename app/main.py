from fastapi import FastAPI

from app.api.routes import api_router
from app.core.config import settings
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    configure_logging()
    application = FastAPI(title=settings.app_name, debug=settings.debug)
    application.include_router(api_router, prefix=settings.api_v1_prefix)
    return application


app = create_app()
