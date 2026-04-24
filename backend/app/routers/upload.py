import asyncio
import csv
import io
import logging
import uuid
from collections.abc import Generator

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_token, verify_token
from app.config import settings
from app.database import get_db
from app.models import Job, JobResult
from app.routers._job_errors import make_failure_callback
from app.services.rate_limiter import check_rate_limit

router = APIRouter(tags=["upload"])


def parse_csv_streaming(
    file_content: bytes,
    company_col: str,
    location_col: str | None,
) -> Generator[dict[str, str | int | None], None, None]:
    """Stream-parse a CSV, yielding normalised row dicts up to max_rows.

    Each yielded dict contains:
        row_index   (int)       — 0-based index of the CSV data row
        company_name (str)      — value from company_col
        location     (str|None) — value from location_col, or None
    Rows with an empty company_name are skipped.
    Stops after settings.max_rows valid rows.
    """
    text = file_content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    valid_count = 0
    for raw_index, row in enumerate(reader):
        if valid_count >= settings.max_rows:
            break
        company_name = (row.get(company_col) or "").strip()
        if not company_name:
            continue
        location: str | None = None
        if location_col:
            location = (row.get(location_col) or "").strip() or None
        yield {
            "row_index": raw_index,
            "company_name": company_name,
            "location": location,
        }
        valid_count += 1


@router.post("/upload")
async def upload_csv(
    request: Request,
    file: UploadFile,
    company_column: str = Form(...),
    location_column: str = Form(default=""),
    email_capture_id: str = Form(...),
    enrich_contacts: bool = Form(default=False),
    job_titles: str = Form(default=""),
    max_contacts: int = Form(default=1),
    serper_api_key: str = Form(default=""),
    quickenrich_api_key: str = Form(default=""),
    token_payload: dict[str, str | int] = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str | int]:
    # --- file type validation ---
    filename = file.filename or ""
    if not filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only .csv files are accepted.",
        )

    # --- size validation ---
    file_content = await file.read()
    max_bytes = settings.max_file_size_mb * 1024 * 1024
    if len(file_content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {settings.max_file_size_mb} MB limit.",
        )

    # --- parse rows ---
    loc_col: str | None = location_column.strip() or None
    rows = list(parse_csv_streaming(file_content, company_column, loc_col))
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No valid rows found in the uploaded CSV.",
        )

    # --- resolve email from token ---
    email = str(token_payload["sub"])

    # --- rate-limit per IP and per email ---
    ip_address: str = request.client.host if request.client else "unknown"
    await check_rate_limit(db, ip_address, "ip", "upload")
    await check_rate_limit(db, email, "email", "upload")

    # --- create Job ---
    # Parse job_titles — frontend sends JSON string like '["CEO","Founder"]'
    import json as _json
    parsed_titles: list[str] = []
    if job_titles:
        try:
            parsed_titles = _json.loads(job_titles)
        except _json.JSONDecodeError:
            parsed_titles = [t.strip() for t in job_titles.split(",") if t.strip()]

    job_config: dict[str, str | int | bool | list[str]] = {
        "company_column": company_column,
        "location_column": location_column,
        "email_capture_id": email_capture_id,
        "enrich_contacts": enrich_contacts,
        "job_titles": parsed_titles,
        "max_contacts": max_contacts,
        "serper_api_key": serper_api_key,
        "quickenrich_api_key": quickenrich_api_key,
    }
    job = Job(
        email_capture_id=uuid.UUID(email_capture_id),
        tool_slug="company-enrichment",
        status="pending",
        total_rows=len(rows),
        config=job_config,
    )
    db.add(job)
    await db.flush()  # populate job.id before creating children

    # --- create JobResult rows ---
    job_results = [
        JobResult(
            job_id=job.id,
            row_index=int(row["row_index"]),
            input_data={
                "company_name": str(row["company_name"]),
                "location": str(row["location"]) if row["location"] is not None else "",
            },
            status="pending",
        )
        for row in rows
    ]
    db.add_all(job_results)
    await db.flush()

    # --- dispatch pipeline ---
    from app.workers.pipeline import run_pipeline

    logger = logging.getLogger(__name__)

    task = asyncio.create_task(run_pipeline({}, str(job.id)))
    task.add_done_callback(make_failure_callback(job.id, logger, "Company Intel pipeline"))

    # --- return response ---
    new_token = create_token(email, str(job.id))
    return {
        "job_id": str(job.id),
        "total_rows": len(rows),
        "token": new_token,
    }
