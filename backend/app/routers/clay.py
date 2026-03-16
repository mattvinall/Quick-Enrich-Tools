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

_BATCH_SIZE = 100


class ClayPushRequest(BaseModel):
    webhook_url: str


class ClayPushResponse(BaseModel):
    pushed: int
    failed: int
    total: int


def _build_record(result: JobResult) -> dict[str, str]:
    """Map a JobResult row to a flat dict for Clay webhook."""
    input_data: dict[str, str] = result.input_data or {}
    contacts_list = result.contacts if isinstance(result.contacts, list) else []
    first_contact: dict[str, str] = contacts_list[0] if contacts_list else {}

    record: dict[str, str] = {
        "company_name": input_data.get("company_name", ""),
        "location": input_data.get("location", ""),
        "website": result.normalized_domain or result.verified_domain or "",
        "verification_confidence": str(result.verification_confidence) if result.verification_confidence is not None else "",
        "status": result.status or "",
    }

    if first_contact:
        record["contact_first_name"] = first_contact.get("first_name", "")
        record["contact_last_name"] = first_contact.get("last_name", "")
        record["contact_title"] = first_contact.get("title", "")
        record["contact_email"] = first_contact.get("email", "")
        record["contact_phone"] = first_contact.get("phone") or first_contact.get("employee_phone", "")
        record["contact_linkedin"] = first_contact.get("linkedin_url") or first_contact.get("employee_linkedin", "")

    return record


@router.post("/clay-push/{job_id}", response_model=ClayPushResponse)
async def clay_push(
    job_id: uuid.UUID,
    body: ClayPushRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _token: Annotated[dict[str, str | int], Depends(verify_token)],
) -> ClayPushResponse:
    """Push completed job results to Clay via webhook URL in batches."""
    job_result = await db.execute(select(Job).where(Job.id == job_id))
    job = job_result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if job.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job is not completed (current status: {job.status})",
        )

    rows_result = await db.execute(
        select(JobResult).where(
            JobResult.job_id == job_id,
            JobResult.normalized_domain.isnot(None),
            JobResult.normalized_domain != "",
        )
    )
    results = rows_result.scalars().all()

    total = len(results)
    pushed = 0
    failed = 0

    async with httpx.AsyncClient(timeout=30.0) as client:
        for batch_start in range(0, total, _BATCH_SIZE):
            batch = results[batch_start: batch_start + _BATCH_SIZE]
            records = [_build_record(r) for r in batch]
            try:
                response = await client.post(
                    body.webhook_url,
                    json=records,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
                pushed += len(batch)
            except httpx.HTTPError:
                failed += len(batch)

    return ClayPushResponse(pushed=pushed, failed=failed, total=total)
