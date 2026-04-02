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
from app.routers import intel
from app.routers import g2
from app.routers import maps
from app.routers import funding


async def _run_arq_worker() -> None:
    """Start the ARQ worker in-process."""
    from arq import Worker
    from app.workers.pipeline import WorkerSettings as P2WorkerSettings
    from app.workers.intel_pipeline import run_intel_pipeline
    from app.workers.g2_pipeline import run_g2_pipeline
    from app.workers.maps_pipeline import run_maps_pipeline
    from app.workers.funding_pipeline import run_funding_pipeline

    all_functions = list(P2WorkerSettings.functions) + [run_intel_pipeline, run_g2_pipeline, run_maps_pipeline, run_funding_pipeline]

    worker = Worker(
        functions=all_functions,
        redis_settings=P2WorkerSettings.redis_settings,
        max_jobs=P2WorkerSettings.max_jobs,
        job_timeout=P2WorkerSettings.job_timeout,
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
app.include_router(intel.router, prefix="/api/v1")
app.include_router(g2.router, prefix="/api/v1")
app.include_router(maps.router, prefix="/api/v1")
app.include_router(funding.router, prefix="/api/v1")


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
