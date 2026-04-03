"""API endpoints for the Google Maps to Company Intel tool."""

import csv
import io
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

router = APIRouter(prefix="/maps", tags=["maps"])


# ── Request / Response Models ────────────────────────────────────────

class ExtractionOptions(BaseModel):
    industry_description: bool = True
    target_market: bool = True
    company_people: bool = True
    homepage_raw_text: bool = False


class MapsSearchItem(BaseModel):
    search_term: str
    location: str


class MapsExtractRequest(BaseModel):
    # Interactive mode
    search_terms: list[str] = []
    location: str = ""
    # CSV mode (overrides search_terms + location if present)
    searches: list[MapsSearchItem] = []
    # Shared config
    max_per_search: int = 20
    options: ExtractionOptions = ExtractionOptions()
    quickenrich_api_key: str = ""
    job_titles: list[str] = []
    max_contacts: int = 3


# ── Endpoints ────────────────────────────────────────────────────────

@router.post("/extract")
async def submit_maps_extraction(
    body: MapsExtractRequest,
    token_payload: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Validate inputs, create Job, and launch maps_pipeline."""
    # Normalize: convert interactive mode into searches list
    if body.searches:
        searches = [s.model_dump() for s in body.searches]
    elif body.search_terms and body.location:
        searches = [
            {"search_term": t.strip(), "location": body.location.strip()}
            for t in body.search_terms
            if t.strip()
        ]
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide either search_terms + location, or a searches list.",
        )

    if not searches:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one search term is required.",
        )

    if len(searches) > 500:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Maximum 500 search term + location combinations.",
        )

    max_per = body.max_per_search
    if max_per < 1 or max_per > 20:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="max_per_search must be between 1 and 20.",
        )

    total_expected = len(searches) * max_per
    if total_expected > 50_000:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Expected {total_expected} results exceeds the 50,000 limit. Reduce search terms or max per search.",
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
        "searches": searches,
        "max_per_search": max_per,
        "options": opts.model_dump(),
        "quickenrich_api_key": body.quickenrich_api_key,
        "job_titles": body.job_titles,
        "max_contacts": body.max_contacts,
    }

    job = Job(
        email_capture_id=uuid.UUID(email_capture_id),
        tool_slug="maps-intel",
        status="pending",
        total_rows=0,  # Updated after Maps discovery
        config=job_config,
    )
    db.add(job)
    await db.flush()

    # Run pipeline as background task
    import asyncio
    from app.workers.maps_pipeline import run_maps_pipeline
    asyncio.create_task(run_maps_pipeline({}, str(job.id)))

    new_token = create_token(email, str(job.id))
    return {
        "job_id": str(job.id),
        "total_searches": len(searches),
        "token": new_token,
    }


# ── CSV Download ─────────────────────────────────────────────────────

_BATCH_SIZE = 500
_MAPS_COLUMNS = [
    "search_term", "location", "business_name", "category",
    "maps_address", "maps_phone", "website", "rating", "review_count",
    "latitude", "longitude", "google_maps_url", "status",
]
_CONTACT_COLUMNS = ["contact_title", "first_name", "last_name", "email", "phone", "linkedin"]


def _extract_maps_rows(result: JobResult, options: dict) -> list[list[str]]:
    """Return one CSV row per contact. Companies with no contacts get one row with empty contact fields."""
    input_data = result.input_data or {}
    extracted = result.extracted_data or {}

    maps_base = [
        str(input_data.get("search_term", "")),
        str(input_data.get("location", "")),
        str(input_data.get("business_name", "")),
        str(input_data.get("category", "")),
        str(input_data.get("maps_address", "")),
        str(input_data.get("maps_phone", "")),
        result.normalized_domain or result.raw_domain or "",
        str(input_data.get("rating") or ""),
        str(input_data.get("review_count") or ""),
        str(input_data.get("latitude") or ""),
        str(input_data.get("longitude") or ""),
        str(input_data.get("google_maps_url", "")),
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

    if options.get("company_people"):
        generic_emails = extracted.get("general_emails") or []
        if not isinstance(generic_emails, list):
            generic_emails = []
        intel_cells.append(", ".join(generic_emails))

    if options.get("homepage_raw_text"):
        intel_cells.append(str(extracted.get("homepage_raw_text") or ""))

    prefix = maps_base + intel_cells

    raw_contacts = result.contacts
    all_contacts: list[dict] = []
    if isinstance(raw_contacts, list):
        all_contacts = [c for c in raw_contacts if isinstance(c, dict)]

    if not all_contacts:
        return [prefix + ["", "", "", "", "", ""]]

    rows: list[list[str]] = []
    for contact in all_contacts:
        contact_cells = [
            contact.get("title", ""),
            contact.get("first_name", ""),
            contact.get("last_name", ""),
            contact.get("email", ""),
            contact.get("phone", ""),
            contact.get("linkedin_url", ""),
        ]
        rows.append(prefix + contact_cells)
    return rows


def _build_maps_headers(options: dict) -> list[str]:
    headers = list(_MAPS_COLUMNS)

    if options.get("industry_description"):
        headers.extend(["industry", "niche", "description", "address", "phone", "general_emails"])

    if options.get("target_market"):
        headers.extend(["target_market", "case_studies"])

    if options.get("company_people"):
        headers.append("generic_emails")

    if options.get("homepage_raw_text"):
        headers.append("homepage_raw_text")

    headers.extend(_CONTACT_COLUMNS)

    return headers


async def _stream_maps_csv(job: Job, db: AsyncSession) -> AsyncGenerator[bytes, None]:
    yield b"\xef\xbb\xbf"

    config = job.config or {}
    options = config.get("options", {})

    headers = _build_maps_headers(options)

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
            for csv_row in _extract_maps_rows(result, options):
                writer.writerow(csv_row)
        yield buf.getvalue().encode("utf-8")

        if len(rows) < _BATCH_SIZE:
            break
        offset += _BATCH_SIZE


@router.get("/download/{job_id}")
async def download_maps_results(
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
    filename = f"maps_intel_results_{timestamp}.csv"

    return StreamingResponse(
        _stream_maps_csv(job, db),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
