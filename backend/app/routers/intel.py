"""API endpoints for the Company/People Intel by URL tool."""

import csv
import io
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Annotated

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_token, verify_token
from app.config import settings
from app.database import get_db
from app.models import Job, JobResult

router = APIRouter(prefix="/intel", tags=["intel"])


class ExtractionOptions(BaseModel):
    industry_description: bool = True
    target_market: bool = True
    company_people: bool = True
    homepage_raw_text: bool = False


class ExtractRequest(BaseModel):
    lines: list[str]
    options: ExtractionOptions
    job_titles: list[str] = []
    max_contacts: int = 3


@router.post("/extract")
async def submit_extraction(
    body: ExtractRequest,
    token_payload: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Accept a list of URLs/company names and start the intel extraction pipeline."""
    import tldextract

    lines = [line.strip() for line in body.lines if line.strip()]
    if not lines:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No valid lines provided.",
        )

    if len(lines) > settings.max_rows:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Maximum {settings.max_rows} lines allowed.",
        )

    opts = body.options
    if not any([opts.industry_description, opts.target_market, opts.company_people, opts.homepage_raw_text]):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one extraction option must be selected.",
        )

    has_names = False
    parsed_lines = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        is_url = False
        if stripped.lower().startswith("http://") or stripped.lower().startswith("https://"):
            is_url = True
        else:
            ext = tldextract.extract(stripped)
            if ext.domain and ext.suffix:
                is_url = True

        input_type = "url" if is_url else "name"
        if input_type == "name":
            has_names = True

        parsed_lines.append({
            "row_index": i,
            "input": stripped,
            "input_type": input_type,
        })

    email = str(token_payload["sub"])
    email_capture_id = str(token_payload.get("job_id", ""))

    job_config = {
        "options": opts.model_dump(),
        "job_titles": body.job_titles,
        "max_contacts": body.max_contacts,
    }

    job = Job(
        email_capture_id=uuid.UUID(email_capture_id),
        tool_slug="company-intel",
        status="pending",
        total_rows=len(parsed_lines),
        config=job_config,
    )
    db.add(job)
    await db.flush()

    job_results = [
        JobResult(
            job_id=job.id,
            row_index=pl["row_index"],
            input_data={"input": pl["input"], "input_type": pl["input_type"]},
            status="pending",
        )
        for pl in parsed_lines
    ]
    db.add_all(job_results)
    await db.flush()

    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    redis_pool = await create_pool(redis_settings)
    try:
        await redis_pool.enqueue_job("run_intel_pipeline", str(job.id))
    finally:
        await redis_pool.aclose()

    new_token = create_token(email, str(job.id))
    return {
        "job_id": str(job.id),
        "total_rows": len(parsed_lines),
        "token": new_token,
    }


_BATCH_SIZE = 500
_BASE_COLUMNS = ["input", "website", "status"]
_CONTACT_FIELDS = ["Title", "First Name", "Last Name", "Email", "Phone", "LinkedIn"]


def _extract_intel_row(result: JobResult, options: dict, max_contacts: int = 5) -> list[str]:
    input_data = result.input_data or {}
    extracted = result.extracted_data or {}

    original_input = input_data.get("input", "")
    website = result.normalized_domain or result.raw_domain or ""
    row_status = result.status

    base = [original_input, website, row_status]

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

    return base + intel_cells + contact_cells


def _build_intel_headers(options: dict, max_contacts: int = 5) -> list[str]:
    headers = list(_BASE_COLUMNS)

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


async def _stream_intel_csv(job: Job, db: AsyncSession) -> AsyncGenerator[bytes, None]:
    yield b"\xef\xbb\xbf"

    config = job.config or {}
    options = config.get("options", {})

    headers = _build_intel_headers(options)

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
            writer.writerow(_extract_intel_row(result, options))
        yield buf.getvalue().encode("utf-8")

        if len(rows) < _BATCH_SIZE:
            break
        offset += _BATCH_SIZE


@router.get("/download/{job_id}")
async def download_intel_results(
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
    filename = f"company_intel_results_{timestamp}.csv"

    return StreamingResponse(
        _stream_intel_csv(job, db),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
