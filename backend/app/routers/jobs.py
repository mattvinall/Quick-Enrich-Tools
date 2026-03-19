import asyncio
import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import verify_token
from app.config import settings
from app.database import AsyncSessionLocal, get_db
from app.models import Job, JobResult

_ALGORITHM = "HS256"

router = APIRouter(tags=["jobs"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class JobStatusResponse(BaseModel):
    id: str
    status: str
    total_rows: int | None
    processed_rows: int
    current_phase: str | None
    phase_progress: float | None
    config: dict[str, str] | None
    error_message: str | None
    started_at: str | None
    completed_at: str | None
    created_at: str


class PreviewRow(BaseModel):
    row_index: int
    company_name: str | None
    location: str | None
    domain: str | None
    confidence: str | None
    status: str
    contacts: list[dict[str, str | None]] | None


class PreviewResponse(BaseModel):
    rows: list[PreviewRow]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _job_or_404(job: Job | None) -> Job:
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


def _assert_token_owns_job(payload: dict[str, str | int], job: Job) -> None:
    """Raise 403 if the token's job_id does not match this job."""
    token_job_id = str(payload.get("job_id", ""))
    if token_job_id != str(job.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


def _build_preview_row(result: JobResult) -> PreviewRow:
    input_data: dict[str, str] = result.input_data or {}

    company_name: str | None = input_data.get("company_name") or input_data.get("Company Name")
    location: str | None = input_data.get("location") or input_data.get("Location")

    domain: str | None = result.normalized_domain or result.verified_domain or None

    confidence: str | None = (
        str(result.verification_confidence) if result.verification_confidence is not None else None
    )

    contacts: list[dict[str, str | None]] | None = None
    if isinstance(result.contacts, list):
        contacts = result.contacts

    return PreviewRow(
        row_index=result.row_index,
        company_name=company_name,
        location=location,
        domain=domain,
        confidence=confidence,
        status=result.status,
        contacts=contacts,
    )


# ---------------------------------------------------------------------------
# GET /jobs/{job_id}
# ---------------------------------------------------------------------------


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: uuid.UUID,
    payload: Annotated[dict[str, str | int], Depends(verify_token)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JobStatusResponse:
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = _job_or_404(result.scalar_one_or_none())
    _assert_token_owns_job(payload, job)

    phase_progress: float | None = None
    if isinstance(job.phase_progress, dict):
        raw = job.phase_progress.get("progress")
        if isinstance(raw, (int, float)):
            phase_progress = float(raw)

    config: dict[str, str] | None = None
    if isinstance(job.config, dict):
        config = {k: v for k, v in job.config.items() if isinstance(v, str)} or None

    return JobStatusResponse(
        id=str(job.id),
        status=job.status,
        total_rows=job.total_rows,
        processed_rows=job.processed_rows,
        current_phase=job.current_phase,
        phase_progress=phase_progress,
        config=config,
        error_message=job.error_message,
        started_at=job.started_at.isoformat() if job.started_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
        created_at=job.created_at.isoformat(),
    )


# ---------------------------------------------------------------------------
# GET /jobs/{job_id}/sse
# ---------------------------------------------------------------------------


@router.get("/jobs/{job_id}/sse")
async def job_sse(
    job_id: uuid.UUID,
    token: str = Query(...),
) -> StreamingResponse:
    try:
        payload: dict[str, str | int] = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[_ALGORITHM],
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc

    token_job_id = str(payload.get("job_id", ""))
    if token_job_id != str(job_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    async def event_stream() -> object:
        while True:
            async with AsyncSessionLocal() as session:
                job_result = await session.execute(select(Job).where(Job.id == job_id))
                job = job_result.scalar_one_or_none()

                if job is None:
                    data = json.dumps({"error": "Job not found"})
                    yield f"data: {data}\n\n"
                    return

                found_count_result = await session.execute(
                    select(func.count(JobResult.id)).where(
                        JobResult.job_id == job_id,
                        JobResult.normalized_domain.isnot(None),
                    )
                )
                found_count: int = found_count_result.scalar_one() or 0

                # Send phase_progress as {current_phase: {done, total}} for frontend
                phase_progress_out: dict = {}
                if isinstance(job.phase_progress, dict) and job.current_phase:
                    phase_progress_out = {job.current_phase: job.phase_progress}

                event_data = json.dumps({
                    "status": job.status,
                    "processed_rows": job.processed_rows,
                    "total_rows": job.total_rows,
                    "current_phase": job.current_phase,
                    "phase_progress": phase_progress_out,
                    "found_count": found_count,
                })
                yield f"data: {event_data}\n\n"

                if job.status in ("completed", "failed"):
                    return

            await asyncio.sleep(2)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# GET /jobs/{job_id}/preview
# ---------------------------------------------------------------------------


@router.get("/jobs/{job_id}/preview", response_model=PreviewResponse)
async def get_job_preview(
    job_id: uuid.UUID,
    payload: Annotated[dict[str, str | int], Depends(verify_token)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(default=50, le=5000, ge=1),
    offset: int = Query(default=0, ge=0),
) -> PreviewResponse:
    job_result = await db.execute(select(Job).where(Job.id == job_id))
    job = _job_or_404(job_result.scalar_one_or_none())
    _assert_token_owns_job(payload, job)

    rows_query = (
        select(JobResult)
        .where(
            JobResult.job_id == job_id,
            JobResult.status != "pending",
        )
        .order_by(JobResult.row_index.desc())
        .limit(limit)
        .offset(offset)
    )

    count_query = (
        select(func.count(JobResult.id))
        .where(
            JobResult.job_id == job_id,
            JobResult.status != "pending",
        )
    )

    rows_result = await db.execute(rows_query)
    count_result = await db.execute(count_query)

    rows = rows_result.scalars().all()
    total: int = count_result.scalar_one() or 0

    return PreviewResponse(
        rows=[_build_preview_row(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
