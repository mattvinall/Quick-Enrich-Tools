"""API endpoints for G2 Category to Company/People Intel tool."""

import asyncio
import csv
import io
import logging
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

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
from app.services.g2_categories import (
    get_all_categories,
    get_all_parents,
    get_categories_by_parent,
    get_category_by_slug,
    search_categories,
)

router = APIRouter(prefix="/g2", tags=["g2"])
logger = logging.getLogger(__name__)


# ── Request / Response Models ────────────────────────────────────────

class ExtractionOptions(BaseModel):
    industry_description: bool = True
    target_market: bool = True
    company_people: bool = True
    homepage_raw_text: bool = False


class G2ExtractRequest(BaseModel):
    categories: list[str]
    max_per_category: int = 250
    options: ExtractionOptions
    quickenrich_api_key: str = ""
    serper_api_key: str = ""
    scrape_do_api_key: str = ""
    job_titles: list[str] = []
    max_contacts: int = 3


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("/categories")
async def list_categories(
    search: str = Query(default="", description="Search query"),
    parent: str = Query(default="", description="Filter by parent group"),
) -> dict:
    """Return G2 category registry. No auth required."""
    if parent:
        cats = get_categories_by_parent(parent)
    elif search:
        cats = search_categories(search)
    else:
        cats = get_all_categories()

    parents = get_all_parents()
    return {"categories": cats, "parents": parents, "total": len(cats)}


@router.post("/extract")
async def submit_g2_extraction(
    body: G2ExtractRequest,
    token_payload: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Validate categories, create Job, and launch g2_pipeline."""
    # Validate categories
    valid_slugs = []
    for slug in body.categories:
        cat = get_category_by_slug(slug)
        if cat is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown G2 category: {slug}",
            )
        valid_slugs.append(slug)

    if not valid_slugs:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one G2 category must be selected.",
        )

    if len(valid_slugs) > 50:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Maximum 50 categories per extraction.",
        )

    opts = body.options
    if not any([opts.industry_description, opts.target_market, opts.company_people, opts.homepage_raw_text]):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one extraction option must be selected.",
        )

    if body.max_per_category < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="max_per_category must be at least 1.",
        )

    email = str(token_payload["sub"])
    email_capture_id = str(token_payload.get("job_id", ""))

    job_config = {
        "categories": valid_slugs,
        "max_per_category": body.max_per_category,
        "options": opts.model_dump(),
        "quickenrich_api_key": body.quickenrich_api_key,
        "serper_api_key": body.serper_api_key,
        "scrape_do_api_key": body.scrape_do_api_key,
        "job_titles": body.job_titles,
        "max_contacts": body.max_contacts,
    }

    job = Job(
        email_capture_id=uuid.UUID(email_capture_id),
        tool_slug="g2-intel",
        status="pending",
        total_rows=0,  # Updated after G2 scrape discovers actual count
        config=job_config,
    )
    db.add(job)
    await db.commit()

    # Run pipeline as background task (same pattern as intel.py)
    from app.workers.g2_pipeline import run_g2_pipeline

    task = asyncio.create_task(run_g2_pipeline({}, str(job.id)))
    register_pipeline_task(task, job.id, logger, "G2 pipeline")

    new_token = create_token(email, str(job.id))
    return {
        "job_id": str(job.id),
        "total_rows": 0,
        "token": new_token,
    }


# ── CSV Download ─────────────────────────────────────────────────────

def _sanitize_csv(value: str) -> str:
    """Prevent CSV injection by prefixing formula-triggering characters."""
    if value and value[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


_BATCH_SIZE = 500
_BASE_COLUMNS = ["g2_category", "g2_url", "g2_rating", "g2_review_count", "input", "website", "status", "intel_extracted"]
_CONTACT_COLUMNS = ["contact_title", "first_name", "last_name", "email", "phone", "mobile", "linkedin"]


def _intel_extracted_flag(extracted: dict) -> str:
    """True when homepage scrape + LLM produced any intel field. See funding.py for context."""
    if not isinstance(extracted, dict):
        return "false"
    intel_keys = ("industry", "niche", "description", "target_market", "case_studies", "homepage_raw_text")
    return "true" if any(extracted.get(k) for k in intel_keys) else "false"


def _extract_g2_rows(result: JobResult, options: dict) -> list[list[str]]:
    """Return one CSV row per contact. Companies with no contacts get one row with empty contact fields."""
    input_data = result.input_data or {}
    extracted = result.extracted_data or {}

    g2_category = _sanitize_csv(input_data.get("g2_category", ""))
    g2_url = input_data.get("g2_url", "")
    g2_rating = str(input_data.get("g2_rating") or "")
    g2_review_count = str(input_data.get("g2_review_count") or "")
    original_input = _sanitize_csv(input_data.get("input", ""))
    website = result.normalized_domain or result.raw_domain or ""
    row_status = result.status

    base = [g2_category, g2_url, g2_rating, g2_review_count, original_input, website, row_status, _intel_extracted_flag(extracted)]

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

    prefix = base + intel_cells

    raw_contacts = result.contacts
    all_contacts: list[dict] = []
    if isinstance(raw_contacts, list):
        all_contacts = [c for c in raw_contacts if isinstance(c, dict)]

    if not all_contacts:
        return [prefix + ["", "", "", "", "", "", ""]]

    rows: list[list[str]] = []
    for contact in all_contacts:
        contact_cells = [
            _sanitize_csv(contact.get("title", "")),
            _sanitize_csv(contact.get("first_name", "")),
            _sanitize_csv(contact.get("last_name", "")),
            _sanitize_csv(contact.get("email", "")),
            _sanitize_csv(contact.get("phone", "")),
            _sanitize_csv(contact.get("mobile", "")),
            _sanitize_csv(contact.get("linkedin_url", "")),
        ]
        rows.append(prefix + contact_cells)
    return rows


def _build_g2_headers(options: dict) -> list[str]:
    headers = list(_BASE_COLUMNS)

    if options.get("industry_description"):
        headers.extend(["industry", "niche", "description", "address", "company_phone", "general_emails"])

    if options.get("target_market"):
        headers.extend(["target_market", "case_studies"])

    if options.get("homepage_raw_text"):
        headers.append("homepage_raw_text")

    headers.extend(_CONTACT_COLUMNS)

    return headers


async def _stream_g2_csv(job: Job, db: AsyncSession) -> AsyncGenerator[bytes, None]:
    yield b"\xef\xbb\xbf"

    config = job.config or {}
    options = config.get("options", {})

    headers = _build_g2_headers(options)

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
            for csv_row in _extract_g2_rows(result, options):
                writer.writerow(csv_row)
        yield buf.getvalue().encode("utf-8")

        if len(rows) < _BATCH_SIZE:
            break
        offset += _BATCH_SIZE


@router.get("/download/{job_id}")
async def download_g2_results(
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
    filename = f"g2_intel_results_{timestamp}.csv"

    return StreamingResponse(
        _stream_g2_csv(job, db),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
