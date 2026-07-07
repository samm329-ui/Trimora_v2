from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from backend.config.settings import settings
from backend.pipelines.orchestrator import Orchestrator
from backend.storage.job_store import JobStore
from backend.utils.logging import configure_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app):
    configure_logging()
    app.state.job_store = JobStore(settings.jobs_root)

    # LLM scheduler is initialized lazily inside ProductionPipeline
    app.state.orchestrator = Orchestrator(app.state.job_store)
    logger.info("Orchestrator started (LLM scheduler will init on first job)")

    yield

    logger.info("Shutdown complete")
