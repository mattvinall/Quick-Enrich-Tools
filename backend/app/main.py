import asyncio
import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger(__name__)

from app.config import settings
from app.database import engine
from app.routers import clay, download, email_capture, jobs, tools, upload


async def _run_arq_worker() -> None:
    """Start the ARQ worker in-process."""
    from arq import Worker
    from app.workers.pipeline import WorkerSettings

    worker = Worker(
        functions=WorkerSettings.functions,
        redis_settings=WorkerSettings.redis_settings,
        max_jobs=WorkerSettings.max_jobs,
        job_timeout=WorkerSettings.job_timeout,
    )
    logger.info("ARQ worker starting in-process")
    await worker.async_run()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Start ARQ worker as a background task
    worker_task = asyncio.create_task(_run_arq_worker())
    logger.info("ARQ worker task created")
    yield
    # Shutdown: cancel the worker and dispose the DB pool
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    await engine.dispose()


app = FastAPI(
    title="QuickEnrich API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(email_capture.router, prefix="/api/v1")
app.include_router(upload.router, prefix="/api/v1")
app.include_router(jobs.router, prefix="/api/v1")
app.include_router(download.router, prefix="/api/v1")
app.include_router(clay.router, prefix="/api/v1")
app.include_router(tools.router, prefix="/api/v1")


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
