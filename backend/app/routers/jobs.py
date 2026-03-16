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


def _resolve_domain(output_data: dict[str, str] | None) -> str | None:
    if not output_data:
        return None
    return (
        output_data.get("normalized_domain")
        or output_data.get("verified_domain")
        or output_data.get("website")
        or None
    )


def _build_preview_row(result: JobResult) -> PreviewRow:
    input_data: dict[str, str] = result.input_data or {}
    output_data: dict[str, str] | None = result.output_data

    company_name: str | None = input_data.get("company_name") or input_data.get("Company Name")
    location: str | None = input_data.get("location") or input_data.get("Location")

    confidence: str | None = None
    contacts: list[dict[str, str | None]] | None = None

    if output_data:
        confidence = output_data.get("confidence") or output_data.get("verification_confidence")
        raw_contacts = output_data.get("contacts")
        if isinstance(raw_contacts, list):
            contacts = raw_contacts
        elif isinstance(raw_contacts, str):
            try:
                parsed = json.loads(raw_contacts)
                if isinstance(parsed, list):
                    contacts = parsed
            except (json.JSONDecodeError, ValueError):
                contacts = None

    return PreviewRow(
        row_index=result.row_index,
        company_name=company_name,
        location=location,
        domain=_resolve_domain(output_data),
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

    output_meta: dict[str, str | float] | None = None
    if job.column_mapping:
        output_meta = job.column_mapping.get("_meta")  # type: ignore[assignment]

    current_phase: str | None = None
    phase_progress: float | None = None
    started_at: str | None = None

    if isinstance(output_meta, dict):
        current_phase = output_meta.get("current_phase")  # type: ignore[assignment]
        raw_progress = output_meta.get("phase_progress")
        if isinstance(raw_progress, (int, float)):
            phase_progress = float(raw_progress)
        started_at = output_meta.get("started_at")  # type: ignore[assignment]

    config: dict[str, str] | None = None
    if job.column_mapping:
        config = {k: v for k, v in job.column_mapping.items() if k != "_meta" and isinstance(v, str)}

    return JobStatusResponse(
        id=str(job.id),
        status=job.status,
        total_rows=job.row_count,
        processed_rows=job.processed_count,
        current_phase=current_phase,
        phase_progress=phase_progress,
        config=config or None,
        error_message=job.error_message,
        started_at=started_at,
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
                        JobResult.output_data["normalized_domain"].astext.isnot(None),
                    )
                )
                found_count: int = found_count_result.scalar_one() or 0

                output_meta: dict[str, str | float] = {}
                if job.column_mapping and isinstance(job.column_mapping.get("_meta"), dict):
                    output_meta = job.column_mapping["_meta"]  # type: ignore[assignment]

                current_phase: str | None = output_meta.get("current_phase")  # type: ignore[assignment]
                raw_progress = output_meta.get("phase_progress")
                phase_progress: float | None = float(raw_progress) if isinstance(raw_progress, (int, float)) else None

                event_data = json.dumps({
                    "status": job.status,
                    "processed_rows": job.processed_count,
                    "total_rows": job.row_count,
                    "current_phase": current_phase,
                    "phase_progress": phase_progress,
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
    limit: int = Query(default=50, le=100, ge=1),
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
