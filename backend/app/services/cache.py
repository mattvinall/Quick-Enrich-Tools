import hashlib
import json
import logging

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

_redis_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    """Return the Redis singleton, creating it on first call."""
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


def make_cache_key(prefix: str, *args: str) -> str:
    """Build a cache key as a SHA-256 hash of the joined arguments."""
    raw = ":".join(args)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return f"{prefix}:{digest}"


async def cache_get(key: str) -> dict[str, object] | None:
    """Fetch a JSON-encoded value from Redis. Returns None on miss or error."""
    try:
        client = get_redis()
        raw = await client.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as exc:
        logger.debug("cache_get failed for %s: %s", key[:30], exc)
        return None


async def cache_set(
    key: str,
    value: dict[str, object],
    ttl_days: int | None = None,
) -> None:
    """Serialise value to JSON and store in Redis with an optional TTL."""
    try:
        client = get_redis()
        days = ttl_days if ttl_days is not None else settings.cache_ttl_days
        ttl_seconds = days * 86_400
        await client.set(key, json.dumps(value), ex=ttl_seconds)
    except Exception as exc:
        logger.debug("cache_set failed for %s: %s", key[:30], exc)
