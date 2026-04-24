"""API endpoints for the Funded Companies Today tool."""

import asyncio
import csv
import io
import logging
import time
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_token, verify_token
from app.config import settings
from app.database import AsyncSessionLocal, get_db
from app.models import Job, JobResult
from app.services.funding_discovery import discover_funded_companies

router = APIRouter(prefix="/funding", tags=["funding"])
logger = logging.getLogger(__name__)


async def _mark_job_failed_on_error(job_id: uuid.UUID, exc: BaseException) -> None:
    """Set Job.status='failed' and record the error so the UI can surface it.

    Two-phase write: if the combined status+error_message commit fails (e.g. the
    original crash was a CheckViolation on the status column), retry writing
    only error_message so the UI still shows something useful instead of hanging.
    """
    message = f"Pipeline crashed: {type(exc).__name__}: {exc}"
    try:
        async with AsyncSessionLocal() as db:
            job_result = await db.execute(select(Job).where(Job.id == job_id))
            job = job_result.scalar_one()
            job.status = "failed"
            job.error_message = message
            await db.commit()
        return
    except Exception as inner:
        logger.error(
            "Failed to mark job %s status=failed after pipeline error: %s",
            job_id, inner,
        )

    try:
        async with AsyncSessionLocal() as db:
            job_result = await db.execute(select(Job).where(Job.id == job_id))
            job = job_result.scalar_one()
            job.error_message = message
            await db.commit()
    except Exception as inner2:
        logger.error(
            "Fallback error_message write also failed for job %s: %s",
            job_id, inner2,
        )

# In-memory rate limiter for the unauthenticated /discover endpoint
_discover_rate: dict[str, list[float]] = {}
_DISCOVER_MAX_REQUESTS = 10
_DISCOVER_WINDOW_SECONDS = 60


def _check_discover_rate_limit(client_ip: str) -> None:
    """Allow up to _DISCOVER_MAX_REQUESTS per IP per rolling window."""
    now = time.monotonic()
    timestamps = _discover_rate.get(client_ip, [])
    # Prune old entries
    timestamps = [t for t in timestamps if now - t < _DISCOVER_WINDOW_SECONDS]
    if len(timestamps) >= _DISCOVER_MAX_REQUESTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Try again later.",
        )
    timestamps.append(now)
    _discover_rate[client_ip] = timestamps

    # Prune stale IPs to prevent unbounded growth
    stale_keys = [
        k for k, v in _discover_rate.items()
        if all(t < now - _DISCOVER_WINDOW_SECONDS for t in v)
    ]
    for k in stale_keys:
        del _discover_rate[k]


# ── Request / Response Models ────────────────────────────────────────

class ExtractionOptions(BaseModel):
    industry_description: bool = True
    target_market: bool = True
    company_people: bool = True
    homepage_raw_text: bool = False


class FundingCompany(BaseModel):
    company_name: str
    funding_amount: str = ""
    funding_round: str = ""
    lead_investor: str = ""
    description_snippet: str = ""
    source_url: str = ""
    source_name: str = ""


class FundingExtractRequest(BaseModel):
    companies: list[FundingCompany]
    options: ExtractionOptions = ExtractionOptions()
    quickenrich_api_key: str = ""
    job_titles: list[str] = []
    max_contacts: int = 3


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("/discover")
async def discover_funding(
    request: Request,
    hours: int = Query(default=24, description="Look back window in hours (1-168)"),
) -> dict:
    """Discover companies funded in the last N hours.

    Accepts hours in [1, 168] so the UI can offer 24h/48h/3d/7d ranges.
    """
    _check_discover_rate_limit(request.client.host if request.client else "unknown")
    if hours < 1 or hours > 168:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="hours must be between 1 and 168 (inclusive).",
        )
    companies = await discover_funded_companies(hours)
    return {"companies": companies, "total": len(companies)}


@router.post("/extract")
async def submit_funding_extraction(
    body: FundingExtractRequest,
    token_payload: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Validate inputs, create Job, and launch funding_pipeline."""
    if not body.companies:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one company must be selected.",
        )

    if len(body.companies) > 500:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Maximum 500 companies per extraction.",
        )

    opts = body.options
    if not any([opts.industry_description, opts.target_market, opts.company_people, opts.homepage_raw_text]):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one extraction option must be selected.",
        )

    email = str(token_payload["sub"])
    email_capture_id = str(token_payload.get("job_id", ""))

    companies_data = [c.model_dump() for c in body.companies]

    job_config = {
        "companies": companies_data,
        "options": opts.model_dump(),
        "quickenrich_api_key": body.quickenrich_api_key,
        "job_titles": body.job_titles,
        "max_contacts": body.max_contacts,
    }

    job = Job(
        email_capture_id=uuid.UUID(email_capture_id),
        tool_slug="funding-intel",
        status="pending",
        total_rows=0,
        config=job_config,
    )
    db.add(job)
    await db.commit()

    from app.workers.funding_pipeline import run_funding_pipeline

    def _on_done(t: asyncio.Task) -> None:
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            logger.error("Pipeline failed for job %s: %s", job.id, exc)
            asyncio.create_task(_mark_job_failed_on_error(job.id, exc))

    task = asyncio.create_task(run_funding_pipeline({}, str(job.id)))
    task.add_done_callback(_on_done)

    new_token = create_token(email, str(job.id))
    return {
        "job_id": str(job.id),
        "total_companies": len(companies_data),
        "token": new_token,
    }


# ── CSV Download ─────────────────────────────────────────────────────

def _sanitize_csv(value: str) -> str:
    """Prevent CSV injection by prefixing formula-triggering characters."""
    if value and value[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


_BATCH_SIZE = 500
_FUNDING_COLUMNS = [
    "company_name", "funding_amount", "funding_round", "lead_investor",
    "funding_description", "source_url", "source_name", "website", "status",
]
_CONTACT_COLUMNS = ["contact_title", "first_name", "last_name", "email", "phone", "linkedin"]


def _extract_funding_rows(result: JobResult, options: dict) -> list[list[str]]:
    """Return one CSV row per contact. Companies with no contacts get one row with empty contact fields."""
    input_data = result.input_data or {}
    extracted = result.extracted_data or {}

    funding_base = [
        _sanitize_csv(str(input_data.get("company_name", ""))),
        str(input_data.get("funding_amount") or ""),
        str(input_data.get("funding_round", "")),
        _sanitize_csv(str(input_data.get("lead_investor") or "")),
        str(input_data.get("funding_description") or ""),
        str(input_data.get("source_url", "")),
        str(input_data.get("source_name", "")),
        result.normalized_domain or result.raw_domain or "",
        result.status,
    ]

    intel_cells: list[str] = []
    if options.get("industry_description"):
        intel_cells.append(str(extracted.get("industry") or ""))
        intel_cells.append(str(extracted.get("niche") or ""))
        intel_cells.append(str(extracted.get("description") or ""))
        intel_cells.append(str(extracted.get("address") or ""))
        intel_cells.append(str(extracted.get("phone") or ""))
        emails = extracted.get("general_emails") or []
        intel_cells.append(", ".join(emails) if isinstance(emails, list) else str(emails))

    if options.get("target_market"):
        intel_cells.append(str(extracted.get("target_market") or ""))
        case_studies = extracted.get("case_studies") or []
        intel_cells.append(", ".join(case_studies) if isinstance(case_studies, list) else str(case_studies))

    if options.get("homepage_raw_text"):
        intel_cells.append(str(extracted.get("homepage_raw_text") or ""))

    prefix = funding_base + intel_cells

    raw_contacts = result.contacts
    all_contacts: list[dict] = []
    if isinstance(raw_contacts, list):
        all_contacts = [c for c in raw_contacts if isinstance(c, dict)]

    if not all_contacts:
        return [prefix + ["", "", "", "", "", ""]]

    rows: list[list[str]] = []
    for contact in all_contacts:
        contact_cells = [
            _sanitize_csv(contact.get("title", "")),
            _sanitize_csv(contact.get("first_name", "")),
            _sanitize_csv(contact.get("last_name", "")),
            _sanitize_csv(contact.get("email", "")),
            contact.get("phone", ""),
            contact.get("linkedin_url", ""),
        ]
        rows.append(prefix + contact_cells)
    return rows


def _build_funding_headers(options: dict) -> list[str]:
    headers = list(_FUNDING_COLUMNS)

    if options.get("industry_description"):
        headers.extend(["industry", "niche", "description", "address", "company_phone", "general_emails"])

    if options.get("target_market"):
        headers.extend(["target_market", "case_studies"])

    if options.get("homepage_raw_text"):
        headers.append("homepage_raw_text")

    headers.extend(_CONTACT_COLUMNS)

    return headers


async def _stream_funding_csv(job: Job, db: AsyncSession) -> AsyncGenerator[bytes, None]:
    yield b"\xef\xbb\xbf"

    config = job.config or {}
    options = config.get("options", {})

    headers = _build_funding_headers(options)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    yield buf.getvalue().encode("utf-8")

    offset = 0
    while True:
        batch_query = (
            select(JobResult)
            .where(JobResult.job_id == job.id)
            .order_by(JobResult.row_index)
            .limit(_BATCH_SIZE)
            .offset(offset)
        )
        batch_result = await db.execute(batch_query)
        rows = batch_result.scalars().all()

        if not rows:
            break

        buf = io.StringIO()
        writer = csv.writer(buf)
        for result in rows:
            for csv_row in _extract_funding_rows(result, options):
                writer.writerow(csv_row)
        yield buf.getvalue().encode("utf-8")

        if len(rows) < _BATCH_SIZE:
            break
        offset += _BATCH_SIZE


@router.get("/download/{job_id}")
async def download_funding_results(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    token: str = Query(default=""),
) -> StreamingResponse:
    from jose import JWTError, jwt as jose_jwt

    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    try:
        payload = jose_jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    job_result = await db.execute(select(Job).where(Job.id == job_id))
    job = job_result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if str(payload.get("job_id", "")) != str(job.id):
        raise HTTPException(status_code=403, detail="Access denied")
    if job.status != "completed":
        raise HTTPException(status_code=400, detail="Job is not yet completed")

    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"funding_intel_results_{timestamp}.csv"

    return StreamingResponse(
        _stream_funding_csv(job, db),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
