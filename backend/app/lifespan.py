from __future__ import annotations

from contextlib import asynccontextmanager

from backend.config.settings import settings
from backend.pipelines.orchestrator import Orchestrator
from backend.storage.job_store import JobStore
from backend.utils.logging import configure_logging


@asynccontextmanager
async def lifespan(app):
    configure_logging()
    app.state.job_store = JobStore(settings.jobs_root)
    app.state.orchestrator = Orchestrator(app.state.job_store)
    yield
