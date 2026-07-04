from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from backend.config.settings import settings
from backend.execution.engine import ExecutionEngine
from backend.execution.provider_session import ProviderSession
from backend.pipelines.orchestrator import Orchestrator
from backend.services.llm_provider import create_provider
from backend.storage.job_store import JobStore
from backend.utils.logging import configure_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app):
    configure_logging()
    app.state.job_store = JobStore(settings.jobs_root)

    # Create execution engine once at app start
    provider = create_provider(settings.semantic_provider)
    session = ProviderSession(provider, capacity=5500)
    engine = ExecutionEngine(session, max_concurrent=3)
    await engine.start(num_workers=3)
    app.state.engine = engine
    logger.info("ExecutionEngine started")

    app.state.orchestrator = Orchestrator(app.state.job_store, engine=engine)

    yield

    # Shutdown: stop the engine
    await engine.stop()
    logger.info("ExecutionEngine stopped")
