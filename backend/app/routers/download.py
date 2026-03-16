import csv
import io
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import verify_token
from app.database import get_db
from app.models import Job, JobResult

router = APIRouter(tags=["download"])

_BATCH_SIZE = 500
_BASE_COLUMNS = ["company_name", "location", "website", "verification_confidence", "status"]
_CONTACT_FIELDS = ["First Name", "Last Name", "Email", "Phone", "LinkedIn"]


def _job_or_404(job: Job | None) -> Job:
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


def _assert_token_owns_job(payload: dict[str, str | int], job: Job) -> None:
    token_job_id = str(payload.get("job_id", ""))
    if token_job_id != str(job.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


def _collect_job_titles(column_mapping: dict[str, str] | None) -> list[str]:
    """Return the ordered list of contact job titles from the job's column_mapping."""
    if not column_mapping:
        return []
    titles: list[str] = []
    for key, value in column_mapping.items():
        if key.startswith("contact_title_") and isinstance(value, str) and value not in titles:
            titles.append(value)
    return titles


def _build_contact_headers(titles: list[str]) -> list[str]:
    headers: list[str] = []
    for title in titles:
        for field in _CONTACT_FIELDS:
            headers.append(f"{title} - {field}")
    return headers


def _extract_row(result: JobResult, titles: list[str]) -> list[str]:
    input_data: dict[str, str] = result.input_data or {}
    output_data: dict[str, str] = result.output_data or {}

    company_name = (
        input_data.get("company_name")
        or input_data.get("Company Name")
        or ""
    )
    location = (
        input_data.get("location")
        or input_data.get("Location")
        or ""
    )
    website = (
        output_data.get("normalized_domain")
        or output_data.get("verified_domain")
        or output_data.get("website")
        or input_data.get("website")
        or ""
    )
    confidence = output_data.get("verification_confidence") or output_data.get("confidence") or ""
    row_status = result.status

    base: list[str] = [company_name, location, website, confidence, row_status]

    contacts_by_title: dict[str, dict[str, str]] = {}
    raw_contacts = output_data.get("contacts")
    if isinstance(raw_contacts, list):
        for contact in raw_contacts:
            if isinstance(contact, dict):
                title = contact.get("job_title") or contact.get("title") or ""
                contacts_by_title[title] = contact

    contact_cells: list[str] = []
    for title in titles:
        contact = contacts_by_title.get(title, {})
        for field in _CONTACT_FIELDS:
            field_key = field.lower().replace(" ", "_")
            contact_cells.append(contact.get(field_key) or contact.get(field) or "")

    return base + contact_cells


async def _stream_csv(job: Job, db: AsyncSession) -> AsyncGenerator[bytes, None]:
    # UTF-8 BOM for Excel compatibility
    yield b"\xef\xbb\xbf"

    titles = _collect_job_titles(job.column_mapping)
    headers = _BASE_COLUMNS + _build_contact_headers(titles)

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
            writer.writerow(_extract_row(result, titles))
        yield buf.getvalue().encode("utf-8")

        if len(rows) < _BATCH_SIZE:
            break
        offset += _BATCH_SIZE


@router.get("/download/{job_id}")
async def download_results(
    job_id: uuid.UUID,
    payload: Annotated[dict[str, str | int], Depends(verify_token)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StreamingResponse:
    job_result = await db.execute(select(Job).where(Job.id == job_id))
    job = _job_or_404(job_result.scalar_one_or_none())
    _assert_token_owns_job(payload, job)

    if job.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job is not yet completed",
        )

    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"website_finder_results_{timestamp}.csv"

    return StreamingResponse(
        _stream_csv(job, db),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
