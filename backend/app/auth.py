from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import settings

_ALGORITHM = "HS256"
_bearer_scheme = HTTPBearer()


def create_token(email: str, job_id: str) -> str:
    """Create a signed JWT for the given email and job_id."""
    now = datetime.now(tz=timezone.utc)
    payload: dict[str, str | int] = {
        "sub": email,
        "job_id": job_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=settings.jwt_expiry_hours)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGORITHM)


def verify_token(
    credentials: HTTPAuthorizationCredentials = Security(_bearer_scheme),
) -> dict[str, str | int]:
    """FastAPI dependency — validates the Bearer JWT and returns its payload."""
    token = credentials.credentials
    try:
        payload: dict[str, str | int] = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[_ALGORITHM],
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    return payload
