"""Shared async retry utility with exponential backoff and jitter."""

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx

logger = logging.getLogger(__name__)

T = TypeVar("T")

RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


def _retry_delay_from_response(
    response: httpx.Response,
    attempt: int,
    base_delay: float,
    max_delay: float,
) -> float:
    """Honor Retry-After if present, else exponential backoff with jitter."""
    retry_after = response.headers.get("retry-after")
    if retry_after:
        try:
            return min(max(float(retry_after), 0.0), max_delay)
        except ValueError:
            pass  # Non-numeric (HTTP-date) — fall through to backoff.
    return min(base_delay * (2 ** attempt) + random.uniform(0, 0.5), max_delay)


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    *,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 15.0,
    retryable_exceptions: tuple[type[Exception], ...] = (),
) -> T:
    """Call *fn* with retries on transient failures.

    Retries on:
    - httpx.HTTPStatusError with status in RETRYABLE_STATUS_CODES
    - Any exception type listed in *retryable_exceptions*

    Uses exponential backoff with jitter between retries.
    """
    for attempt in range(max_retries + 1):
        try:
            return await fn()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in RETRYABLE_STATUS_CODES and attempt < max_retries:
                delay = _retry_delay_from_response(
                    exc.response, attempt, base_delay, max_delay,
                )
                logger.warning(
                    "Retry %d/%d after HTTP %d, delay=%.1fs",
                    attempt + 1,
                    max_retries,
                    exc.response.status_code,
                    delay,
                )
                await asyncio.sleep(delay)
            else:
                raise
        except retryable_exceptions as exc:
            if attempt < max_retries:
                delay = min(base_delay * (2 ** attempt) + random.uniform(0, 0.5), max_delay)
                logger.warning(
                    "Retry %d/%d after %s, delay=%.1fs",
                    attempt + 1,
                    max_retries,
                    type(exc).__name__,
                    delay,
                )
                await asyncio.sleep(delay)
            else:
                raise

    raise RuntimeError("retry_async exhausted without returning or raising")
