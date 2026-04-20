"""Async retry with exponential backoff + jitter."""

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx

logger = logging.getLogger(__name__)
T = TypeVar("T")

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    *,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 15.0,
) -> T:
    for attempt in range(max_retries + 1):
        try:
            return await fn()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in RETRYABLE_STATUS and attempt < max_retries:
                delay = min(base_delay * (2 ** attempt) + random.uniform(0, 0.5), max_delay)
                logger.warning(
                    "Retry %d/%d after HTTP %d (delay=%.1fs)",
                    attempt + 1, max_retries, exc.response.status_code, delay,
                )
                await asyncio.sleep(delay)
            else:
                raise
    raise RuntimeError("retry_async exhausted")
