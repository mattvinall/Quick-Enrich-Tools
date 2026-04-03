import csv
import io
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import verify_token
from app.database import get_db
from app.models import Job, JobResult

router = APIRouter(tags=["download"])

_BATCH_SIZE = 500
_BASE_COLUMNS = ["company_name", "location", "website", "verification_confidence", "status"]
_CONTACT_COLUMNS = ["contact_title", "first_name", "last_name", "email", "phone", "linkedin"]


def _job_or_404(job: Job | None) -> Job:
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


def _assert_token_owns_job(payload: dict[str, str | int], job: Job) -> None:
    token_job_id = str(payload.get("job_id", ""))
    if token_job_id != str(job.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


def _extract_rows(result: JobResult) -> list[list[str]]:
    """Return one CSV row per contact. Companies with no contacts get one row with empty contact fields."""
    input_data: dict[str, str] = result.input_data or {}

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
    website = result.normalized_domain or result.verified_domain or ""
    confidence = str(result.verification_confidence) if result.verification_confidence is not None else ""
    row_status = result.status

    base: list[str] = [company_name, location, website, confidence, row_status]

    raw_contacts = result.contacts
    all_contacts: list[dict[str, str]] = []
    if isinstance(raw_contacts, list):
        all_contacts = [c for c in raw_contacts if isinstance(c, dict)]

    if not all_contacts:
        return [base + ["", "", "", "", "", ""]]

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
        rows.append(base + contact_cells)
    return rows


async def _stream_csv(job: Job, db: AsyncSession) -> AsyncGenerator[bytes, None]:
    # UTF-8 BOM for Excel compatibility
    yield b"\xef\xbb\xbf"

    headers = _BASE_COLUMNS + _CONTACT_COLUMNS

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
            for csv_row in _extract_rows(result):
                writer.writerow(csv_row)
        yield buf.getvalue().encode("utf-8")

        if len(rows) < _BATCH_SIZE:
            break
        offset += _BATCH_SIZE


@router.get("/download/{job_id}")
async def download_results(
    job_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    token: str = Query(default=""),
) -> StreamingResponse:
    from jose import JWTError, jwt as jose_jwt
    from app.config import settings as app_settings

    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    try:
        payload = jose_jwt.decode(token, app_settings.jwt_secret, algorithms=["HS256"])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
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
