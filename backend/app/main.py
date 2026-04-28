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
from app.routers import people


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    if settings.jwt_secret == "change-me":
        raise RuntimeError(
            "JWT_SECRET is set to the default 'change-me'. "
            "Set a strong secret via the JWT_SECRET environment variable."
        )

    yield
    await engine.dispose()


app = FastAPI(
    title="QuickEnrich API",
    version="1.0.0",
    lifespan=lifespan,
)

_frontend_origins = [
    origin.strip()
    for origin in settings.frontend_url.split(",")
    if origin.strip()
]
_allowed_origins = list({*_frontend_origins, "http://localhost:3000"})

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_origin_regex=r"^https://([a-z0-9-]+\.)*quickenrich\.io$",
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
app.include_router(people.router, prefix="/api/v1")


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
