"""API endpoints for the People Intel by Name tool."""

import asyncio
import csv
import io
import logging
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_token, verify_token
from app.config import settings
from app.database import get_db
from app.models import Job, JobResult
from app.routers._job_errors import register_pipeline_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/people", tags=["people"])


# ── Request / Response Models ────────────────────────────────────────


class ExtractionOptions(BaseModel):
    industry_description: bool = True
    target_market: bool = True
    company_people: bool = True
    homepage_raw_text: bool = False


class PeopleItem(BaseModel):
    full_name: str
    company_name: str
    website: str | None = None


class PeopleExtractRequest(BaseModel):
    items: list[PeopleItem]
    options: ExtractionOptions
    serper_api_key: str = ""
    quickenrich_api_key: str = ""
    scrape_do_api_key: str = ""
    job_titles: list[str] = []
    max_contacts: int = 3


# ── Endpoints ────────────────────────────────────────────────────────


@router.post("/extract")
async def submit_people_extraction(
    body: PeopleExtractRequest,
    token_payload: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Validate input, create Job + JobResult rows, launch pipeline."""
    items = [item for item in body.items if item.full_name.strip() and item.company_name.strip()]
    if not items:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No valid items provided. Each item needs a name and company.",
        )

    if len(items) > settings.max_rows:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Maximum {settings.max_rows} items allowed.",
        )

    opts = body.options
    if not any([opts.industry_description, opts.target_market, opts.company_people, opts.homepage_raw_text]):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one extraction option must be selected.",
        )

    email = str(token_payload["sub"])
    email_capture_id = str(token_payload.get("job_id", ""))

    job_config = {
        "options": opts.model_dump(),
        "serper_api_key": body.serper_api_key,
        "quickenrich_api_key": body.quickenrich_api_key,
        "scrape_do_api_key": body.scrape_do_api_key,
        "job_titles": body.job_titles,
        "max_contacts": body.max_contacts,
    }

    job = Job(
        email_capture_id=uuid.UUID(email_capture_id),
        tool_slug="people-intel",
        status="pending",
        total_rows=len(items),
        config=job_config,
    )
    db.add(job)
    await db.flush()

    job_results = [
        JobResult(
            job_id=job.id,
            row_index=i,
            input_data={
                "full_name": item.full_name.strip(),
                "company_name": item.company_name.strip(),
                "website": (item.website or "").strip(),
                "input_type": "url" if item.website else "name",
            },
            status="pending",
        )
        for i, item in enumerate(items)
    ]
    db.add_all(job_results)
    await db.flush()

    # Run pipeline as background task
    from app.workers.people_pipeline import run_people_pipeline

    task = asyncio.create_task(run_people_pipeline({}, str(job.id)))
    register_pipeline_task(task, job.id, logger, "People pipeline")

    new_token = create_token(email, str(job.id))
    return {
        "job_id": str(job.id),
        "total_rows": len(items),
        "token": new_token,
    }


# ── CSV Download ─────────────────────────────────────────────────────

_BATCH_SIZE = 500
# People Intel is 1:1 — one input row maps to one person and (at most) one
# contact, so the CSV uses a single un-numbered contact_* column block instead
# of the contact_1_… contact_5_ pattern that Company Intel uses for many-per-co.
_BASE_COLUMNS = ["full_name", "company_name", "linkedin_url", "linkedin_confidence", "website", "status"]
_CONTACT_COLUMNS = [
    "contact_title",
    "contact_first_name",
    "contact_last_name",
    "contact_email",
    "contact_phone",
    "contact_linkedin",
]


def _sanitize_csv(value: str) -> str:
    """Prevent CSV injection by prefixing formula-triggering characters."""
    if value and value[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def _extract_people_row(result: JobResult, options: dict) -> list[str]:
    input_data = result.input_data or {}
    extracted = result.extracted_data or {}

    full_name = _sanitize_csv(input_data.get("full_name", ""))
    company_name = _sanitize_csv(input_data.get("company_name", ""))
    # Phase 0 (LinkedIn search) stashes linkedin_url / linkedin_confidence here
    # because the intel pipeline's resolve phase overwrites search_results.
    linkedin_url = input_data.get("linkedin_url", "") or ""
    confidence = input_data.get("linkedin_confidence", "")
    confidence_str = str(confidence) if confidence != "" else ""
    website = result.normalized_domain or result.raw_domain or ""
    row_status = result.status

    base = [full_name, company_name, linkedin_url, confidence_str, website, row_status]

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

    raw_contacts = result.contacts
    contact: dict = {}
    if isinstance(raw_contacts, list):
        for c in raw_contacts:
            if isinstance(c, dict):
                contact = c
                break

    contact_cells = [
        _sanitize_csv(contact.get("title", "")),
        _sanitize_csv(contact.get("first_name", "")),
        _sanitize_csv(contact.get("last_name", "")),
        _sanitize_csv(contact.get("email", "")),
        contact.get("phone", "") or "",
        contact.get("linkedin_url", "") or "",
    ]

    return base + intel_cells + contact_cells


def _build_people_headers(options: dict) -> list[str]:
    headers = list(_BASE_COLUMNS)

    if options.get("industry_description"):
        headers.extend(["industry", "niche", "description", "address", "company_phone", "general_emails"])

    if options.get("target_market"):
        headers.extend(["target_market", "case_studies"])

    if options.get("homepage_raw_text"):
        headers.append("homepage_raw_text")

    headers.extend(_CONTACT_COLUMNS)

    return headers


async def _stream_people_csv(job: Job, db: AsyncSession) -> AsyncGenerator[bytes, None]:
    yield b"\xef\xbb\xbf"

    config = job.config or {}
    options = config.get("options", {})

    headers = _build_people_headers(options)

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
            writer.writerow(_extract_people_row(result, options))
        yield buf.getvalue().encode("utf-8")

        if len(rows) < _BATCH_SIZE:
            break
        offset += _BATCH_SIZE


@router.get("/download/{job_id}")
async def download_people_results(
    job_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
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
    filename = f"people_intel_results_{timestamp}.csv"

    return StreamingResponse(
        _stream_people_csv(job, db),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
