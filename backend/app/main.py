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

from app.config import settings
from app.database import engine
from app.routers import clay, download, email_capture, jobs, tools, upload


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup: nothing to do — engine is created at import time.
    yield
    # Shutdown: dispose the connection pool cleanly.
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
