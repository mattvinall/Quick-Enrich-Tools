import uuid
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import verify_token
from app.database import get_db
from app.models import Job, JobResult

router = APIRouter(tags=["clay"])

_CLAY_ROWS_URL = "https://api.clay.com/v1/tables/{table_id}/rows"
_BATCH_SIZE = 100


class ClayPushRequest(BaseModel):
    clay_api_key: str
    table_id: str


class ClayPushResponse(BaseModel):
    pushed: int
    failed: int
    total: int


def _build_record(result: JobResult) -> dict[str, object]:
    """Map a JobResult row to a Clay record dict."""
    output: dict[str, object] = result.output_data or {}
    return {
        "company_name": output.get("company_name", ""),
        "location": output.get("location", ""),
        "website": output.get("normalized_domain", ""),
        "confidence": output.get("confidence", ""),
        # Contact fields
        "contact_name": output.get("contact_name", ""),
        "contact_title": output.get("contact_title", ""),
        "contact_email": output.get("contact_email", ""),
        "contact_linkedin": output.get("contact_linkedin", ""),
    }


@router.post("/clay-push/{job_id}", response_model=ClayPushResponse)
async def clay_push(
    job_id: uuid.UUID,
    body: ClayPushRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _token: Annotated[dict[str, str | int], Depends(verify_token)],
) -> ClayPushResponse:
    """Push completed job results to a Clay table in batches of 100."""
    # Verify job exists and is completed
    job_result = await db.execute(select(Job).where(Job.id == job_id))
    job = job_result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if job.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job is not completed (current status: {job.status})",
        )

    # Fetch all results that have a normalized_domain
    rows_result = await db.execute(
        select(JobResult).where(
            JobResult.job_id == job_id,
            JobResult.output_data["normalized_domain"].astext != "",
        )
    )
    results = rows_result.scalars().all()

    total = len(results)
    pushed = 0
    failed = 0

    url = _CLAY_ROWS_URL.format(table_id=body.table_id)
    headers = {
        "Authorization": f"Bearer {body.clay_api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        for batch_start in range(0, total, _BATCH_SIZE):
            batch = results[batch_start : batch_start + _BATCH_SIZE]
            rows = [_build_record(r) for r in batch]
            try:
                response = await client.post(url, headers=headers, json={"rows": rows})
                response.raise_for_status()
                pushed += len(batch)
            except httpx.HTTPError:
                failed += len(batch)

    return ClayPushResponse(pushed=pushed, failed=failed, total=total)
