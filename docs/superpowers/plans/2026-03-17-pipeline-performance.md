# Pipeline Performance Optimization Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Optimize the 5-phase processing pipeline to handle up to 100K rows via phase pipelining, parallel LLM verification, increased concurrency, caching, and retry logic — achieving a 5-8x speedup.

**Architecture:** Replace the strictly sequential phase execution with an `asyncio.Queue`-based pipeline where phases run concurrently on micro-batches. Each phase operates with its own DB session and shared httpx client. A new retry utility handles transient failures across all services.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, asyncio (Queue/Semaphore/gather), httpx, Redis, ARQ, google-generativeai, openai

**Spec:** `docs/superpowers/specs/2026-03-17-pipeline-performance-design.md`

---

## Chunk 1: Foundation (Config, DB Pool, Retry Utility)

### Task 1: Update config.py settings

**Files:**
- Modify: `backend/app/config.py`
- Test: `backend/tests/test_config.py`

- [ ] **Step 1: Write test for new config settings**

Create `backend/tests/test_config.py`:

```python
"""Tests for config settings."""
from app.config import Settings


def test_default_settings_have_pipeline_fields():
    """Verify new pipeline settings exist with correct defaults."""
    s = Settings(
        database_url="postgresql+asyncpg://localhost/test",
        redis_url="redis://localhost",
    )
    assert s.verify_concurrency == 5
    assert s.pipeline_batch_size == 200
    assert s.serper_concurrency == 50
    assert s.enrich_concurrency == 30
    # Removed settings should not exist
    assert not hasattr(s, "llm_concurrency")
    assert not hasattr(s, "search_batch_size")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/MattV/Desktop/projects/Quick-Enrich-Tools/backend && python -m pytest tests/test_config.py -v`
Expected: FAIL — `verify_concurrency` and `pipeline_batch_size` don't exist yet

- [ ] **Step 3: Update config.py**

Modify `backend/app/config.py` — replace lines 22-30:

```python
    serper_concurrency: int = 50
    verify_concurrency: int = 5
    normalize_concurrency: int = 50
    enrich_concurrency: int = 30
    pipeline_batch_size: int = 200
    llm_batch_size: int = 20
    normalize_batch_size: int = 200
    enrich_batch_size: int = 50
    cache_ttl_days: int = 7
```

Remove `llm_concurrency`, `search_batch_size`. Bump `serper_concurrency` from 20→50, `enrich_concurrency` from 10→30. Add `verify_concurrency` and `pipeline_batch_size`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/MattV/Desktop/projects/Quick-Enrich-Tools/backend && python -m pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py backend/tests/test_config.py
git commit -m "feat: update config with pipeline performance settings"
```

---

### Task 2: Increase DB connection pool

**Files:**
- Modify: `backend/app/database.py:11-14`

- [ ] **Step 1: Update pool_size and max_overflow**

In `backend/app/database.py`, change lines 12-14:

```python
engine = create_async_engine(
    settings.database_url,
    pool_size=15,
    max_overflow=5,
```

- [ ] **Step 2: Verify the app still imports cleanly**

Run: `cd /Users/MattV/Desktop/projects/Quick-Enrich-Tools/backend && python -c "from app.database import engine; print('pool_size:', engine.pool.size()); print('OK')"`
Expected: prints `pool_size: 15` and `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/database.py
git commit -m "feat: increase DB pool to 15+5 for concurrent pipeline phases"
```

---

### Task 3: Create shared retry utility

**Files:**
- Create: `backend/app/services/retry.py`
- Test: `backend/tests/test_retry.py`

- [ ] **Step 1: Write tests for retry utility**

Create `backend/tests/test_retry.py`:

```python
"""Tests for async retry utility."""
import pytest
import httpx

from app.services.retry import retry_async


class FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code
        self.request = httpx.Request("GET", "https://example.com")


@pytest.mark.asyncio
async def test_retry_succeeds_on_first_try():
    call_count = 0

    async def fn():
        nonlocal call_count
        call_count += 1
        return "ok"

    result = await retry_async(fn)
    assert result == "ok"
    assert call_count == 1


@pytest.mark.asyncio
async def test_retry_retries_on_429_then_succeeds():
    call_count = 0

    async def fn():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            resp = FakeResponse(429)
            raise httpx.HTTPStatusError("rate limited", request=resp.request, response=resp)
        return "ok"

    result = await retry_async(fn, max_retries=3, base_delay=0.01)
    assert result == "ok"
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_raises_on_non_retryable():
    async def fn():
        resp = FakeResponse(400)
        raise httpx.HTTPStatusError("bad request", request=resp.request, response=resp)

    with pytest.raises(httpx.HTTPStatusError):
        await retry_async(fn, max_retries=3, base_delay=0.01)


@pytest.mark.asyncio
async def test_retry_retries_custom_exceptions():
    call_count = 0

    class CustomError(Exception):
        pass

    async def fn():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise CustomError("transient")
        return "ok"

    result = await retry_async(
        fn, max_retries=3, base_delay=0.01, retryable_exceptions=(CustomError,)
    )
    assert result == "ok"
    assert call_count == 2


@pytest.mark.asyncio
async def test_retry_exhausts_retries():
    async def fn():
        resp = FakeResponse(429)
        raise httpx.HTTPStatusError("rate limited", request=resp.request, response=resp)

    with pytest.raises(httpx.HTTPStatusError):
        await retry_async(fn, max_retries=2, base_delay=0.01)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/MattV/Desktop/projects/Quick-Enrich-Tools/backend && python -m pytest tests/test_retry.py -v`
Expected: FAIL — `app.services.retry` doesn't exist

- [ ] **Step 3: Implement retry utility**

Create `backend/app/services/retry.py`:

```python
"""Shared async retry utility with exponential backoff and jitter."""

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import httpx

logger = logging.getLogger(__name__)

T = TypeVar("T")

RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


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
                delay = min(base_delay * (2 ** attempt) + random.uniform(0, 0.5), max_delay)
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

    # Should never reach here, but satisfy type checker
    raise RuntimeError("retry_async exhausted without returning or raising")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/MattV/Desktop/projects/Quick-Enrich-Tools/backend && python -m pytest tests/test_retry.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/retry.py backend/tests/test_retry.py
git commit -m "feat: add shared async retry utility with exponential backoff"
```

---

## Chunk 2: Service Layer Improvements (Shared Clients, Retry Wrapping, Enrichment Caching)

### Task 4: Add retry + shared client to batch_search()

**Files:**
- Modify: `backend/app/services/serper.py:81-148`
- Test: `backend/tests/test_serper_retry.py`

- [ ] **Step 1: Write test for retry behavior in search**

Create `backend/tests/test_serper_retry.py`:

```python
"""Tests for serper retry and shared client behavior."""
import pytest
import httpx

from app.services.retry import retry_async


@pytest.mark.asyncio
async def test_search_company_retries_on_429(monkeypatch):
    """Verify that search_company wrapped in retry_async retries on 429."""
    call_count = 0

    async def mock_search(client, company, location):
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            resp = httpx.Response(429, request=httpx.Request("POST", "https://example.com"))
            raise httpx.HTTPStatusError("rate limited", request=resp.request, response=resp)
        return {"query": "test", "results": [], "candidate_domain": ""}

    result = await retry_async(
        lambda: mock_search(None, "Acme", "SF"),
        max_retries=3,
        base_delay=0.01,
    )
    assert result["query"] == "test"
    assert call_count == 2
```

- [ ] **Step 2: Run test to verify it passes** (tests retry utility integration)

Run: `cd /Users/MattV/Desktop/projects/Quick-Enrich-Tools/backend && python -m pytest tests/test_serper_retry.py -v`
Expected: PASS

- [ ] **Step 3: Update batch_search() with shared client and retry**

Modify `backend/app/services/serper.py`. Replace the `_search_one` inner function and client creation (lines 102-110):

```python
async def batch_search(
    rows: list[dict[str, object]],
    concurrency: int | None = None,
) -> list[dict[str, object]]:
    """Search each unique company_name/location pair once and map results back."""
    limit = concurrency if concurrency is not None else settings.serper_concurrency
    semaphore = asyncio.Semaphore(limit)

    # Group row indices by their dedup key
    groups: dict[str, list[int]] = {}
    for idx, row in enumerate(rows):
        company_name: str = str(row.get("company_name", ""))
        location: str = str(row.get("location", ""))
        dedup_key = f"{company_name.lower()}|{location.lower()}"
        groups.setdefault(dedup_key, []).append(idx)

    unique_keys = list(groups.keys())

    async with httpx.AsyncClient() as client:

        async def _search_one(dedup_key: str) -> tuple[str, dict[str, object] | BaseException]:
            company_name, _, location = dedup_key.partition("|")
            async with semaphore:
                try:
                    result = await retry_async(
                        lambda cn=company_name, loc=location: search_company(client, cn, loc),
                        max_retries=3,
                        base_delay=1.0,
                    )
                    return dedup_key, result
                except Exception as exc:
                    return dedup_key, exc

        raw_outcomes = await asyncio.gather(
            *[_search_one(key) for key in unique_keys],
            return_exceptions=True,
        )

    # ... rest of mapping logic unchanged ...
```

Add import at top of file: `from app.services.retry import retry_async`

- [ ] **Step 4: Verify existing tests still pass**

Run: `cd /Users/MattV/Desktop/projects/Quick-Enrich-Tools/backend && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/serper.py backend/tests/test_serper_retry.py
git commit -m "feat: shared httpx client + retry in batch_search"
```

---

### Task 5: Add retry + shared client to batch_enrich() + enrichment caching

**Files:**
- Modify: `backend/app/services/enrichment.py`
- Test: `backend/tests/test_enrichment_cache.py`

- [ ] **Step 1: Write test for enrichment caching**

Create `backend/tests/test_enrichment_cache.py`:

```python
"""Tests for enrichment caching logic."""
import pytest

from app.services.cache import make_cache_key


def test_enrich_cache_key_is_deterministic():
    """Same inputs produce same cache key regardless of title order."""
    key1 = make_cache_key("enrich", "example.com", "ceo, cto", "1")
    key2 = make_cache_key("enrich", "example.com", "ceo, cto", "1")
    assert key1 == key2


def test_enrich_cache_key_sorted_titles():
    """Titles should be sorted before hashing for consistency."""
    # This tests the convention: callers must sort titles before calling make_cache_key
    titles_a = ", ".join(sorted(["cto", "ceo"]))
    titles_b = ", ".join(sorted(["ceo", "cto"]))
    key1 = make_cache_key("enrich", "example.com", titles_a, "1")
    key2 = make_cache_key("enrich", "example.com", titles_b, "1")
    assert key1 == key2
```

- [ ] **Step 2: Run test to verify it passes** (tests cache key logic)

Run: `cd /Users/MattV/Desktop/projects/Quick-Enrich-Tools/backend && python -m pytest tests/test_enrichment_cache.py -v`
Expected: PASS

- [ ] **Step 3: Update enrichment.py with caching, shared client, and retry**

Rewrite `backend/app/services/enrichment.py`:

```python
import asyncio
import logging

import httpx

from app.config import settings
from app.services.cache import cache_get, cache_set, make_cache_key
from app.services.retry import retry_async

logger = logging.getLogger(__name__)

_CONTACT_FIELDS = ("title", "first_name", "last_name", "email", "phone", "linkedin_url")


def _enrich_cache_key(domain: str, job_titles: list[str], max_contacts: int) -> str:
    """Build a deterministic cache key for enrichment results."""
    sorted_titles = ", ".join(sorted(t.lower() for t in job_titles))
    return make_cache_key("enrich", domain.lower(), sorted_titles, str(max_contacts))


async def enrich_company(
    client: httpx.AsyncClient,
    domain: str,
    job_titles: list[str],
    max_contacts: int = 1,
) -> list[dict[str, str]]:
    """Fetch contacts from QuickEnrich for a single domain.

    Checks Redis cache first. On cache miss, calls the API and caches the result.
    """
    cache_key = _enrich_cache_key(domain, job_titles, max_contacts)
    cached = await cache_get(cache_key)
    if cached is not None and isinstance(cached, dict):
        logger.info("ENRICH CACHE HIT: %s", domain)
        return cached.get("contacts", [])  # type: ignore[return-value]

    contacts: list[dict[str, str]] = []
    combined_titles = ", ".join(job_titles)

    async def _do_request() -> httpx.Response:
        response = await client.get(
            "https://app.quickenrich.io/api/employees/dataset-search",
            params={"company_url": domain, "title": combined_titles},
            headers={"Authorization": f"Bearer {settings.quickenrich_api_key}"},
            timeout=15.0,
        )
        response.raise_for_status()
        return response

    try:
        response = await retry_async(_do_request, max_retries=3, base_delay=1.0)
        data = response.json()

        if isinstance(data, list):
            raw_results: list[dict[str, object]] = data
        elif isinstance(data, dict):
            raw_results = data.get("data", data.get("results", []))
        else:
            raw_results = []

        for record in raw_results[:max_contacts * len(job_titles)]:
            contacts.append(
                {
                    "title": str(record.get("title") or ""),
                    "first_name": str(record.get("first_name") or ""),
                    "last_name": str(record.get("last_name") or ""),
                    "email": str(record.get("email") or ""),
                    "phone": str(record.get("employee_phone") or record.get("phone") or ""),
                    "linkedin_url": str(
                        record.get("employee_linkedin") or record.get("linkedin_url") or ""
                    ),
                }
            )

        # Only cache successful results — never cache on error
        await cache_set(cache_key, {"contacts": contacts}, settings.cache_ttl_days)
    except Exception as exc:
        logger.warning("enrich_company error for domain=%s titles=%s: %s", domain, combined_titles, exc)

    return contacts


async def batch_enrich(
    domains_with_rows: dict[str, list[int]],
    job_titles: list[str],
    max_contacts: int = 1,
    concurrency: int | None = None,
) -> dict[str, list[dict[str, str]]]:
    """Enrich each unique domain once with a shared httpx client."""
    limit = concurrency if concurrency is not None else settings.enrich_concurrency
    semaphore = asyncio.Semaphore(limit)

    async with httpx.AsyncClient() as client:

        async def _enrich_one(domain: str) -> tuple[str, list[dict[str, str]] | BaseException]:
            async with semaphore:
                try:
                    result = await enrich_company(client, domain, job_titles, max_contacts)
                    return domain, result
                except Exception as exc:
                    return domain, exc

        raw_outcomes = await asyncio.gather(
            *[_enrich_one(domain) for domain in domains_with_rows],
            return_exceptions=True,
        )

    results: dict[str, list[dict[str, str]]] = {}
    for outcome in raw_outcomes:
        if isinstance(outcome, BaseException):
            continue
        domain, value = outcome
        if isinstance(value, BaseException):
            logger.warning("batch_enrich failed for domain=%s: %s", domain, value)
            results[domain] = []
        else:
            results[domain] = value

    return results
```

- [ ] **Step 4: Run all tests**

Run: `cd /Users/MattV/Desktop/projects/Quick-Enrich-Tools/backend && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/enrichment.py backend/tests/test_enrichment_cache.py
git commit -m "feat: add enrichment caching, shared client, and retry"
```

---

### Task 6: Add retry to LLM providers

**Files:**
- Modify: `backend/app/services/llm/gemini.py:65-91`
- Modify: `backend/app/services/llm/openai_provider.py:58-91`

- [ ] **Step 1: Update Gemini provider with retry**

Modify `backend/app/services/llm/gemini.py`. Add import at top:

```python
from app.services.retry import retry_async
```

Replace the `verify_domains` method (lines 65-91):

```python
    async def verify_domains(self, batch: list[dict]) -> list[VerificationResult]:
        prompt = _PROMPT_TEMPLATE.format(items=_build_items_block(batch))

        try:
            from google.api_core import exceptions as google_exceptions

            response = await retry_async(
                lambda: self._model.generate_content_async(prompt),
                max_retries=3,
                base_delay=1.0,
                retryable_exceptions=(
                    google_exceptions.ResourceExhausted,
                    google_exceptions.ServiceUnavailable,
                ),
            )
        except Exception:
            return _fallback(batch)

        raw = response.text.strip()

        try:
            parsed: list[dict] = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return _fallback(batch)

        results: list[VerificationResult] = []
        try:
            for entry in parsed:
                results.append(
                    VerificationResult(
                        row_index=int(entry["row_index"]),
                        match=bool(entry["match"]),
                        confidence=float(entry["confidence"]),
                        reason=str(entry["reason"]),
                        suggested_domain=entry.get("suggested_domain") or None,
                    )
                )
        except (KeyError, TypeError, ValueError):
            return _fallback(batch)

        return results
```

- [ ] **Step 2: Update OpenAI provider with retry**

Modify `backend/app/services/llm/openai_provider.py`. Add import at top:

```python
import openai as openai_module
from app.services.retry import retry_async
```

Replace the `verify_domains` method (lines 58-91):

```python
    async def verify_domains(self, batch: list[dict]) -> list[VerificationResult]:
        prompt = _PROMPT_TEMPLATE.format(items=_build_items_block(batch))

        try:
            response = await retry_async(
                lambda: self._client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    temperature=0.1,
                ),
                max_retries=3,
                base_delay=1.0,
                retryable_exceptions=(
                    openai_module.RateLimitError,
                    openai_module.APIConnectionError,
                    openai_module.InternalServerError,
                ),
            )
        except Exception:
            return _fallback(batch)

        raw = (response.choices[0].message.content or "").strip()

        try:
            parsed_obj: dict = json.loads(raw)
            parsed: list[dict] = parsed_obj["results"]
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return _fallback(batch)

        results: list[VerificationResult] = []
        try:
            for entry in parsed:
                results.append(
                    VerificationResult(
                        row_index=int(entry["row_index"]),
                        match=bool(entry["match"]),
                        confidence=float(entry["confidence"]),
                        reason=str(entry["reason"]),
                        suggested_domain=entry.get("suggested_domain") or None,
                    )
                )
        except (KeyError, TypeError, ValueError):
            return _fallback(batch)

        return results
```

- [ ] **Step 3: Add retry to normalizer resolve_redirect**

Modify `backend/app/services/normalizer.py`. Add import at top:

```python
from app.services.retry import retry_async
```

Replace `resolve_redirect` function (lines 100-115):

```python
async def resolve_redirect(client: httpx.AsyncClient, domain: str) -> str:
    """Follow redirects for https://{domain} and return the final root domain."""
    try:
        response = await retry_async(
            lambda: client.head(
                f"https://{domain}",
                follow_redirects=True,
                timeout=5,
            ),
            max_retries=2,
            base_delay=0.5,
        )
        final_url = str(response.url)
        cleaned = clean_url(final_url)
        return cleaned if cleaned is not None else domain
    except Exception:
        return domain
```

- [ ] **Step 4: Run all tests**

Run: `cd /Users/MattV/Desktop/projects/Quick-Enrich-Tools/backend && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/llm/gemini.py backend/app/services/llm/openai_provider.py backend/app/services/normalizer.py
git commit -m "feat: add retry with backoff to LLM providers and normalizer"
```

---

## Chunk 3: Pipeline Restructure (Pipelining + Parallel LLM)

### Task 7: Rewrite pipeline.py with queue-based pipelining and parallel LLM

This is the largest task — it restructures the entire pipeline orchestration.

**Files:**
- Modify: `backend/app/workers/pipeline.py` (full rewrite)
- Test: `backend/tests/test_pipeline_structure.py`

- [ ] **Step 1: Write structural test for pipeline imports and function signatures**

Create `backend/tests/test_pipeline_structure.py`:

```python
"""Structural tests for the pipelined pipeline module."""
import inspect
import pytest


def test_pipeline_has_required_functions():
    """Verify the restructured pipeline exports expected functions."""
    from app.workers import pipeline

    assert hasattr(pipeline, "run_pipeline")
    assert hasattr(pipeline, "update_job_progress")

    # run_pipeline should be async
    assert inspect.iscoroutinefunction(pipeline.run_pipeline)


def test_worker_settings_exist():
    """WorkerSettings must still be importable for ARQ."""
    from app.workers.pipeline import WorkerSettings

    assert hasattr(WorkerSettings, "functions")
    assert hasattr(WorkerSettings, "max_jobs")
    assert WorkerSettings.max_jobs == 5
```

- [ ] **Step 2: Run test to verify it passes with current code** (sanity check)

Run: `cd /Users/MattV/Desktop/projects/Quick-Enrich-Tools/backend && python -m pytest tests/test_pipeline_structure.py -v`
Expected: PASS (current code already has these)

- [ ] **Step 3: Rewrite pipeline.py**

Replace the entire content of `backend/app/workers/pipeline.py`:

```python
"""ARQ worker — queue-based pipelined processing pipeline.

Phases run concurrently via asyncio.Queue. Each phase has its own DB
session. Queues pass lists of JobResult primary keys (UUIDs) between
phases to avoid ORM staleness.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from arq.connections import RedisSettings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import EmailCapture, Job, JobResult
from app.services.email_service import send_results_email
from app.services.enrichment import batch_enrich
from app.services.llm import get_llm_provider
from app.services.normalizer import batch_normalize
from app.services.serper import batch_search

logger = logging.getLogger(__name__)

# Type alias for items flowing through queues: lists of JobResult UUIDs
QueueItem = list[uuid.UUID] | None  # None = sentinel to shut down


async def update_job_progress(
    db: AsyncSession,
    job_id: uuid.UUID,
    phase: str,
    done: int,
    total: int,
    processed_rows: int | None = None,
) -> None:
    """Update job's current_phase, phase_progress JSONB, and optionally processed_rows."""
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one()
    job.current_phase = phase
    job.phase_progress = {"done": done, "total": total}
    if processed_rows is not None:
        job.processed_rows = processed_rows
    await db.commit()


# ---------------------------------------------------------------------------
# Phase workers — each runs in its own async task with its own DB session
# ---------------------------------------------------------------------------


async def _phase_search_worker(
    job_id: uuid.UUID,
    total_rows: int,
    queue_out: asyncio.Queue[QueueItem],
    error_event: asyncio.Event,
    progress: dict[str, int],
) -> None:
    """Phase 1: Search for candidate domains via Serper."""
    batch_size = settings.pipeline_batch_size

    try:
        async with AsyncSessionLocal() as db:
            for batch_start in range(0, total_rows, batch_size):
                if error_event.is_set():
                    break

                # Load micro-batch of JobResults from DB
                result = await db.execute(
                    select(JobResult)
                    .where(JobResult.job_id == job_id)
                    .order_by(JobResult.row_index)
                    .offset(batch_start)
                    .limit(batch_size)
                )
                batch_results = list(result.scalars().all())
                if not batch_results:
                    break

                rows = [
                    {
                        "row_index": r.row_index,
                        "company_name": r.input_data.get("company_name", ""),
                        "location": r.input_data.get("location", ""),
                    }
                    for r in batch_results
                ]

                search_outcomes = await batch_search(rows)

                outcome_by_row: dict[int, dict[str, object]] = {
                    int(o["row_index"]): o for o in search_outcomes
                }

                result_by_row_index = {r.row_index: r for r in batch_results}

                for idx_in_batch, row in enumerate(rows):
                    original_row_index = row["row_index"]
                    job_result = result_by_row_index[original_row_index]
                    outcome = outcome_by_row.get(idx_in_batch)
                    if outcome is not None:
                        job_result.search_results = outcome.get("search_results")
                        candidate = outcome.get("candidate_domain", "")
                        job_result.raw_domain = str(candidate) if candidate else None
                    job_result.status = "searched"

                await db.commit()

                # Push IDs to next phase
                ids = [r.id for r in batch_results]
                await queue_out.put(ids)

                done = min(batch_start + batch_size, total_rows)
                progress["search"] = done
                await update_job_progress(db, job_id, "search", done, total_rows, processed_rows=done)

    except Exception as exc:
        logger.exception("phase_search_worker failed: %s", exc)
        error_event.set()
        raise
    finally:
        await queue_out.put(None)  # Sentinel


async def _phase_verify_worker(
    job_id: uuid.UUID,
    total_rows: int,
    queue_in: asyncio.Queue[QueueItem],
    queue_out: asyncio.Queue[QueueItem],
    error_event: asyncio.Event,
    progress: dict[str, int],
) -> None:
    """Phase 2: LLM-based domain verification with parallel batches."""
    provider = get_llm_provider()
    verify_sem = asyncio.Semaphore(settings.verify_concurrency)

    async def _verify_batch(items: list[dict[str, object]]) -> list:
        async with verify_sem:
            return await provider.verify_domains(items)

    try:
        async with AsyncSessionLocal() as db:
            total_verified = 0

            while True:
                if error_event.is_set():
                    break

                msg = await queue_in.get()
                if msg is None:
                    break

                result_ids: list[uuid.UUID] = msg

                # Load fresh from DB
                result = await db.execute(
                    select(JobResult).where(JobResult.id.in_(result_ids))
                )
                batch_results = list(result.scalars().all())

                with_domain = [r for r in batch_results if r.raw_domain]
                without_domain = [r for r in batch_results if not r.raw_domain]

                for r in without_domain:
                    r.status = "not_found"
                if without_domain:
                    await db.commit()

                if with_domain:
                    # Build LLM items
                    all_items: list[dict[str, object]] = []
                    for r in with_domain:
                        search_results = r.search_results or {}
                        first_result: dict[str, object] = {}
                        if isinstance(search_results, dict):
                            sr_list = search_results.get("results", [])
                            if isinstance(sr_list, list) and sr_list:
                                first_result = sr_list[0]
                        all_items.append(
                            {
                                "row_index": r.row_index,
                                "company_name": r.input_data.get("company_name", ""),
                                "location": r.input_data.get("location", ""),
                                "candidate_domain": r.raw_domain or "",
                                "search_snippet": str(first_result.get("snippet", "")),
                            }
                        )

                    # Split into LLM batches and run in parallel
                    llm_batch_size = provider.max_batch_size
                    llm_batches = [
                        all_items[i : i + llm_batch_size]
                        for i in range(0, len(all_items), llm_batch_size)
                    ]

                    all_verification_results = await asyncio.gather(
                        *[_verify_batch(b) for b in llm_batches]
                    )

                    result_by_row_index = {r.row_index: r for r in with_domain}

                    for vr_batch in all_verification_results:
                        for vr in vr_batch:
                            job_result = result_by_row_index.get(vr.row_index)
                            if job_result is None:
                                continue
                            job_result.verification_confidence = vr.confidence
                            if vr.match and vr.confidence >= 0.7:
                                job_result.verified_domain = job_result.raw_domain
                                job_result.status = "verified"
                            elif vr.suggested_domain:
                                job_result.verified_domain = vr.suggested_domain
                                job_result.status = "verified"
                            else:
                                job_result.status = "not_found"

                    await db.commit()

                total_verified += len(batch_results)
                progress["verify"] = total_verified
                await update_job_progress(db, job_id, "verify", total_verified, total_rows)

                await queue_out.put(result_ids)

    except Exception as exc:
        logger.exception("phase_verify_worker failed: %s", exc)
        error_event.set()
        raise
    finally:
        await queue_out.put(None)


async def _phase_normalize_worker(
    job_id: uuid.UUID,
    total_rows: int,
    queue_in: asyncio.Queue[QueueItem],
    queue_out: asyncio.Queue[QueueItem],
    error_event: asyncio.Event,
    progress: dict[str, int],
) -> None:
    """Phase 3: Normalize and resolve verified domains."""
    try:
        async with AsyncSessionLocal() as db:
            total_normalized = 0

            while True:
                if error_event.is_set():
                    break

                msg = await queue_in.get()
                if msg is None:
                    break

                result_ids: list[uuid.UUID] = msg

                result = await db.execute(
                    select(JobResult).where(JobResult.id.in_(result_ids))
                )
                batch_results = list(result.scalars().all())

                eligible = [r for r in batch_results if r.verified_domain]

                if eligible:
                    rows = [{"verified_domain": r.verified_domain} for r in eligible]

                    normalize_outcomes = await batch_normalize(
                        rows,
                        resolve_redirects=True,
                        concurrency=settings.normalize_concurrency,
                    )

                    outcome_by_pos = {int(o["row_index"]): o for o in normalize_outcomes}

                    for batch_pos, job_result in enumerate(eligible):
                        outcome = outcome_by_pos.get(batch_pos)
                        if outcome is None:
                            job_result.status = "failed"
                            continue
                        if outcome.get("blocked"):
                            job_result.status = "blocked"
                        elif outcome.get("error") or not outcome.get("domain"):
                            job_result.status = "failed"
                        else:
                            job_result.normalized_domain = str(outcome["domain"])
                            job_result.status = "normalized"

                    await db.commit()

                total_normalized += len(batch_results)
                progress["normalize"] = total_normalized
                await update_job_progress(db, job_id, "normalize", total_normalized, total_rows)

                await queue_out.put(result_ids)

    except Exception as exc:
        logger.exception("phase_normalize_worker failed: %s", exc)
        error_event.set()
        raise
    finally:
        await queue_out.put(None)


async def _phase_enrich_worker(
    job_id: uuid.UUID,
    total_rows: int,
    config: dict[str, object],
    queue_in: asyncio.Queue[QueueItem],
    error_event: asyncio.Event,
    progress: dict[str, int],
    completion_event: asyncio.Event,
) -> None:
    """Phase 4: Contact enrichment grouped by normalized domain."""
    enrich_contacts = config.get("enrich_contacts", False)
    job_titles: list[str] = config.get("job_titles", [])  # type: ignore[assignment]
    max_contacts: int = int(config.get("max_contacts", 1))

    try:
        async with AsyncSessionLocal() as db:
            total_enriched = 0

            while True:
                if error_event.is_set():
                    break

                msg = await queue_in.get()
                if msg is None:
                    break

                result_ids: list[uuid.UUID] = msg

                if not enrich_contacts or not job_titles:
                    total_enriched += len(result_ids)
                    progress["enrich"] = total_enriched
                    continue

                result = await db.execute(
                    select(JobResult).where(JobResult.id.in_(result_ids))
                )
                batch_results = list(result.scalars().all())

                domains_with_rows: dict[str, list[int]] = {}
                for r in batch_results:
                    if r.normalized_domain:
                        domains_with_rows.setdefault(r.normalized_domain, []).append(r.row_index)

                if domains_with_rows:
                    contacts_by_domain = await batch_enrich(
                        domains_with_rows,
                        job_titles=job_titles,
                        max_contacts=max_contacts,
                    )

                    result_by_row_index = {r.row_index: r for r in batch_results}
                    for domain, row_indices in domains_with_rows.items():
                        contacts = contacts_by_domain.get(domain, [])
                        for row_index in row_indices:
                            job_result = result_by_row_index.get(row_index)
                            if job_result is not None:
                                job_result.contacts = contacts  # type: ignore[assignment]
                                job_result.status = "enriched"

                    await db.commit()

                total_enriched += len(result_ids)
                progress["enrich"] = total_enriched
                await update_job_progress(db, job_id, "enrich", total_enriched, total_rows)

    except Exception as exc:
        logger.exception("phase_enrich_worker failed: %s", exc)
        error_event.set()
        raise
    finally:
        completion_event.set()


async def _phase_deliver(
    job_id: uuid.UUID,
) -> None:
    """Phase 5: Send results email to the user."""
    async with AsyncSessionLocal() as db:
        job_result = await db.execute(select(Job).where(Job.id == job_id))
        job = job_result.scalar_one()

        result = await db.execute(
            select(JobResult).where(JobResult.job_id == job_id)
        )
        all_results = list(result.scalars().all())
        found = sum(1 for r in all_results if r.normalized_domain)

        email_capture_result = await db.execute(
            select(EmailCapture).where(EmailCapture.id == job.email_capture_id)
        )
        email_capture = email_capture_result.scalar_one()

        download_url = f"{settings.frontend_url}/jobs/{job_id}/download"
        job_stats: dict[str, int] = {
            "total_rows": job.total_rows,
            "websites_found": found,
        }

        try:
            send_results_email(
                to_email=email_capture.email,
                download_url=download_url,
                job_stats=job_stats,
            )
        except Exception as e:
            logger.warning("Failed to send results email for job_id=%s: %s", job_id, e)

        await update_job_progress(db, job_id, "deliver", 1, 1)


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


async def run_pipeline(ctx: dict[str, object], job_id: str) -> None:
    """Main ARQ entry point — orchestrates the pipelined processing pipeline."""
    parsed_job_id = uuid.UUID(job_id)

    # Read job metadata with a short-lived session
    async with AsyncSessionLocal() as db:
        job_result = await db.execute(select(Job).where(Job.id == parsed_job_id))
        job = job_result.scalar_one()
        total_rows = job.total_rows
        config: dict[str, object] = job.config or {}

        job.status = "searching"
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

    # Bounded queues for backpressure between phases
    queue_sv: asyncio.Queue[QueueItem] = asyncio.Queue(maxsize=5)  # search → verify
    queue_vn: asyncio.Queue[QueueItem] = asyncio.Queue(maxsize=5)  # verify → normalize
    queue_ne: asyncio.Queue[QueueItem] = asyncio.Queue(maxsize=5)  # normalize → enrich

    error_event = asyncio.Event()
    completion_event = asyncio.Event()
    progress: dict[str, int] = {"search": 0, "verify": 0, "normalize": 0, "enrich": 0}

    # Launch all phase workers concurrently
    tasks = [
        asyncio.create_task(
            _phase_search_worker(parsed_job_id, total_rows, queue_sv, error_event, progress),
            name="phase_search",
        ),
        asyncio.create_task(
            _phase_verify_worker(parsed_job_id, total_rows, queue_sv, queue_vn, error_event, progress),
            name="phase_verify",
        ),
        asyncio.create_task(
            _phase_normalize_worker(parsed_job_id, total_rows, queue_vn, queue_ne, error_event, progress),
            name="phase_normalize",
        ),
        asyncio.create_task(
            _phase_enrich_worker(parsed_job_id, total_rows, config, queue_ne, error_event, progress, completion_event),
            name="phase_enrich",
        ),
    ]

    try:
        # Wait for all phase tasks to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check for errors
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                raise result

        # Phase 5: Deliver (runs after all pipeline phases complete)
        async with AsyncSessionLocal() as db:
            job_result = await db.execute(select(Job).where(Job.id == parsed_job_id))
            job = job_result.scalar_one()
            job.status = "delivering"
            await db.commit()

        await _phase_deliver(parsed_job_id)

        # Mark job as completed
        async with AsyncSessionLocal() as db:
            job_result = await db.execute(select(Job).where(Job.id == parsed_job_id))
            job = job_result.scalar_one()
            job.status = "completed"
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()

        logger.info("Pipeline completed for job_id=%s", job_id)

    except Exception as exc:
        logger.exception("Pipeline failed for job_id=%s: %s", job_id, exc)
        error_event.set()

        # Cancel any still-running tasks
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

        try:
            async with AsyncSessionLocal() as db:
                err_result = await db.execute(select(Job).where(Job.id == parsed_job_id))
                failed_job = err_result.scalar_one()
                failed_job.status = "failed"
                failed_job.error_message = str(exc)
                await db.commit()
        except Exception:
            logger.exception("Failed to mark job as failed for job_id=%s", job_id)
        raise


def _parse_redis_settings(redis_url: str) -> RedisSettings:
    """Parse a redis:// or rediss:// URL into an arq RedisSettings instance."""
    from urllib.parse import urlparse

    parsed = urlparse(redis_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 6379
    password = parsed.password or None
    db_index = int(parsed.path.lstrip("/")) if parsed.path and parsed.path != "/" else 0
    use_ssl = parsed.scheme == "rediss"

    return RedisSettings(host=host, port=port, password=password, database=db_index, ssl=use_ssl)


class WorkerSettings:
    functions = [run_pipeline]
    redis_settings = _parse_redis_settings(settings.redis_url)
    max_jobs = 5
    job_timeout = 7200
```

- [ ] **Step 4: Run structural test**

Run: `cd /Users/MattV/Desktop/projects/Quick-Enrich-Tools/backend && python -m pytest tests/test_pipeline_structure.py -v`
Expected: PASS

- [ ] **Step 5: Run all tests**

Run: `cd /Users/MattV/Desktop/projects/Quick-Enrich-Tools/backend && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/workers/pipeline.py backend/tests/test_pipeline_structure.py
git commit -m "feat: rewrite pipeline with queue-based pipelining and parallel LLM verification"
```

---

## Chunk 4: Integration Verification

### Task 8: End-to-end smoke test

**Files:**
- Test: manual verification

- [ ] **Step 1: Verify all imports resolve**

Run: `cd /Users/MattV/Desktop/projects/Quick-Enrich-Tools/backend && python -c "from app.workers.pipeline import run_pipeline, WorkerSettings; print('Pipeline OK')"`
Expected: `Pipeline OK`

- [ ] **Step 2: Verify all config settings**

Run: `cd /Users/MattV/Desktop/projects/Quick-Enrich-Tools/backend && python -c "
from app.config import settings
print('serper_concurrency:', settings.serper_concurrency)
print('verify_concurrency:', settings.verify_concurrency)
print('enrich_concurrency:', settings.enrich_concurrency)
print('pipeline_batch_size:', settings.pipeline_batch_size)
print('OK')
"`
Expected: Shows 50, 5, 30, 200 respectively

- [ ] **Step 3: Run full test suite**

Run: `cd /Users/MattV/Desktop/projects/Quick-Enrich-Tools/backend && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Final commit with all changes**

Verify git status is clean. If any unstaged changes remain, stage and commit.

```bash
git status
```

---

## Summary of All Changes

| File | Change Type | Description |
|------|------------|-------------|
| `backend/app/config.py` | Modified | New: `verify_concurrency`, `pipeline_batch_size`. Removed: `llm_concurrency`, `search_batch_size`. Bumped: `serper_concurrency` 20→50, `enrich_concurrency` 10→30 |
| `backend/app/database.py` | Modified | `pool_size` 5→15, `max_overflow` 0→5 |
| `backend/app/services/retry.py` | **New** | Shared async retry with exponential backoff, jitter, configurable exception types |
| `backend/app/services/serper.py` | Modified | Shared httpx client in `batch_search()`, retry wrapping |
| `backend/app/services/enrichment.py` | Modified | Redis caching, shared httpx client in `batch_enrich()`, retry wrapping |
| `backend/app/services/llm/gemini.py` | Modified | Retry with google SDK exception handling |
| `backend/app/services/llm/openai_provider.py` | Modified | Retry with openai SDK exception handling |
| `backend/app/services/normalizer.py` | Modified | Retry on redirect resolution |
| `backend/app/workers/pipeline.py` | **Rewritten** | Queue-based phase pipelining, per-phase DB sessions, parallel LLM verification |
| `backend/tests/test_config.py` | **New** | Config settings test |
| `backend/tests/test_retry.py` | **New** | Retry utility tests |
| `backend/tests/test_serper_retry.py` | **New** | Serper retry integration test |
| `backend/tests/test_enrichment_cache.py` | **New** | Enrichment cache key test |
| `backend/tests/test_pipeline_structure.py` | **New** | Pipeline structural test |
