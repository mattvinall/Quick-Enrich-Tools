from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import RateLimit

# Maps (identifier_type, action) -> daily limit
LIMITS: dict[tuple[str, str], int] = {
    ("email", "email_capture"): settings.uploads_per_email_per_day,
    ("ip", "email_capture"): settings.uploads_per_ip_per_day,
}


async def check_rate_limit(
    db: AsyncSession,
    identifier: str,
    identifier_type: str,
    action: str,
) -> None:
    """Check and increment rate limit for an identifier within a 24-hour window.

    Raises HTTP 429 if the limit has been reached.
    """
    limit = LIMITS.get((identifier_type, action))
    if limit is None:
        return

    now = datetime.now(tz=timezone.utc)
    window_start = now - timedelta(hours=24)

    result = await db.execute(
        select(RateLimit).where(
            RateLimit.identifier == identifier,
            RateLimit.identifier_type == identifier_type,
            RateLimit.action == action,
            RateLimit.window_start >= window_start,
        )
    )
    record = result.scalar_one_or_none()

    if record is not None:
        if record.request_count >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded for {identifier_type}. Try again later.",
            )
        record.request_count += 1
    else:
        record = RateLimit(
            identifier=identifier,
            identifier_type=identifier_type,
            action=action,
            window_start=now,
            request_count=1,
        )
        db.add(record)
