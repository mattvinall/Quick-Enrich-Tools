from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.auth import create_token
from app.database import get_db
from app.models import EmailCapture
from app.services.rate_limiter import check_rate_limit

router = APIRouter(tags=["email-capture"])


class EmailCaptureRequest(BaseModel):
    email: EmailStr
    tool_slug: str
    source: str | None = None


class EmailCaptureResponse(BaseModel):
    email_capture_id: str
    token: str
    message: str


@router.post("/email-capture", response_model=EmailCaptureResponse)
async def capture_email(
    body: EmailCaptureRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> EmailCaptureResponse:
    ip_address: str = request.client.host if request.client else "unknown"

    await check_rate_limit(db, ip_address, "ip", "email_capture")
    await check_rate_limit(db, body.email, "email", "email_capture")

    stmt = (
        pg_insert(EmailCapture)
        .values(email=body.email)
        .on_conflict_do_update(
            index_elements=["email"],
            set_={"email": body.email},
        )
        .returning(EmailCapture.id)
    )

    result = await db.execute(stmt)
    capture_id = result.scalar_one()

    token = create_token(body.email, str(capture_id))

    return EmailCaptureResponse(
        email_capture_id=str(capture_id),
        token=token,
        message="Email captured successfully",
    )
