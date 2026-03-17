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
_CONTACT_FIELDS = ["Title", "First Name", "Last Name", "Email", "Phone", "LinkedIn"]


def _job_or_404(job: Job | None) -> Job:
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


def _assert_token_owns_job(payload: dict[str, str | int], job: Job) -> None:
    token_job_id = str(payload.get("job_id", ""))
    if token_job_id != str(job.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


def _collect_job_titles(config: dict[str, str | int | bool | list[str]] | None) -> list[str]:
    """Return the ordered list of contact job titles from the job's config."""
    if not config:
        return []
    raw = config.get("job_titles", [])
    if isinstance(raw, list):
        return [str(t) for t in raw if t]
    if isinstance(raw, str):
        import json
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(t) for t in parsed if t]
        except (json.JSONDecodeError, TypeError):
            return [t.strip() for t in raw.split(",") if t.strip()]
    return []


def _build_contact_headers(titles: list[str]) -> list[str]:
    headers: list[str] = []
    for title in titles:
        for field in _CONTACT_FIELDS:
            headers.append(f"{title} - {field}")
    return headers


def _extract_row(result: JobResult, titles: list[str]) -> list[str]:
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

    # Assign contacts to title columns positionally — first contact goes
    # to the first title column, second to the second, etc.
    raw_contacts = result.contacts
    all_contacts: list[dict[str, str]] = []
    if isinstance(raw_contacts, list):
        all_contacts = [c for c in raw_contacts if isinstance(c, dict)]

    contact_cells: list[str] = []
    for idx in range(len(titles)):
        contact = all_contacts[idx] if idx < len(all_contacts) else {}
        contact_cells.append(contact.get("title", ""))
        contact_cells.append(contact.get("first_name", ""))
        contact_cells.append(contact.get("last_name", ""))
        contact_cells.append(contact.get("email", ""))
        contact_cells.append(contact.get("phone", ""))
        contact_cells.append(contact.get("linkedin_url", ""))

    return base + contact_cells


async def _stream_csv(job: Job, db: AsyncSession) -> AsyncGenerator[bytes, None]:
    # UTF-8 BOM for Excel compatibility
    yield b"\xef\xbb\xbf"

    titles = _collect_job_titles(job.config)
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
