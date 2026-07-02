from __future__ import annotations

from fastapi import FastAPI

from backend.api.middleware.cors import add_cors
from backend.api.middleware.errors import error_middleware
from backend.api.middleware.logging import logging_middleware
from backend.api.routes.export import router as export_router
from backend.api.routes.preview import router as preview_router
from backend.api.routes.process import router as process_router
from backend.api.routes.status import router as status_router
from backend.app.lifespan import lifespan
from backend.config.settings import settings


def create_app() -> FastAPI:
    app = FastAPI(title="Trimora Backend", version="1.0.0", lifespan=lifespan)
    add_cors(app, settings.cors_origins)
    app.middleware("http")(logging_middleware)
    app.middleware("http")(error_middleware)

    app.include_router(process_router)
    app.include_router(status_router)
    app.include_router(preview_router)
    app.include_router(export_router)

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "service": "trimora-backend"}

    return app


app = create_app()
