"""API endpoints for the Funded Companies Today tool."""

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
from app.services.funding_discovery import discover_funded_companies

router = APIRouter(prefix="/funding", tags=["funding"])


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
    hours: int = Query(default=24, description="Look back window: 24 or 48 hours"),
) -> dict:
    """Discover companies funded in the last N hours.

    Only accepts hours=24 or hours=48 to limit cache buckets and
    prevent abuse of Serper/Gemini API calls via parameter variation.
    """
    if hours not in (24, 48):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="hours must be 24 or 48.",
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

    import asyncio
    from app.workers.funding_pipeline import run_funding_pipeline
    asyncio.create_task(run_funding_pipeline({}, str(job.id)))

    new_token = create_token(email, str(job.id))
    return {
        "job_id": str(job.id),
        "total_companies": len(companies_data),
        "token": new_token,
    }


# ── CSV Download ─────────────────────────────────────────────────────

_BATCH_SIZE = 500
_FUNDING_COLUMNS = [
    "company_name", "funding_amount", "funding_round", "lead_investor",
    "funding_description", "source_url", "source_name", "website", "status",
]
_CONTACT_FIELDS = ["Title", "First Name", "Last Name", "Email", "Phone", "LinkedIn"]


def _extract_funding_row(result: JobResult, options: dict, max_contacts: int = 5) -> list[str]:
    input_data = result.input_data or {}
    extracted = result.extracted_data or {}

    funding_base = [
        str(input_data.get("company_name", "")),
        str(input_data.get("funding_amount") or ""),
        str(input_data.get("funding_round", "")),
        str(input_data.get("lead_investor") or ""),
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

    if options.get("company_people"):
        generic_emails = extracted.get("general_emails") or []
        if not isinstance(generic_emails, list):
            generic_emails = []
        intel_cells.append(", ".join(generic_emails))

    if options.get("homepage_raw_text"):
        intel_cells.append(str(extracted.get("homepage_raw_text") or ""))

    raw_contacts = result.contacts
    all_contacts: list[dict] = []
    if isinstance(raw_contacts, list):
        all_contacts = [c for c in raw_contacts if isinstance(c, dict)]

    contact_cells: list[str] = []
    for idx in range(max_contacts):
        contact = all_contacts[idx] if idx < len(all_contacts) else {}
        contact_cells.append(contact.get("title", ""))
        contact_cells.append(contact.get("first_name", ""))
        contact_cells.append(contact.get("last_name", ""))
        contact_cells.append(contact.get("email", ""))
        contact_cells.append(contact.get("phone", ""))
        contact_cells.append(contact.get("linkedin_url", ""))

    return funding_base + intel_cells + contact_cells


def _build_funding_headers(options: dict, max_contacts: int = 5) -> list[str]:
    headers = list(_FUNDING_COLUMNS)

    if options.get("industry_description"):
        headers.extend(["industry", "niche", "description", "address", "phone", "general_emails"])

    if options.get("target_market"):
        headers.extend(["target_market", "case_studies"])

    if options.get("company_people"):
        headers.append("generic_emails")

    if options.get("homepage_raw_text"):
        headers.append("homepage_raw_text")

    for i in range(1, max_contacts + 1):
        for field in _CONTACT_FIELDS:
            headers.append(f"contact_{i}_{field.lower().replace(' ', '_')}")

    return headers


async def _stream_funding_csv(job: Job, db: AsyncSession) -> AsyncGenerator[bytes, None]:
    yield b"\xef\xbb\xbf"

    config = job.config or {}
    options = config.get("options", {})
    max_contacts = int(config.get("max_contacts", 5))

    headers = _build_funding_headers(options, max_contacts)

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
            writer.writerow(_extract_funding_row(result, options, max_contacts))
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
