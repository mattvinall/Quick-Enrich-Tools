# Pipeline Performance Optimization Design

**Date:** 2026-03-17
**Status:** Draft
**Goal:** Optimize the 5-phase processing pipeline (Search → Verify → Normalize → Enrich → Deliver) to handle up to 100K rows efficiently through phase pipelining, parallel LLM verification, increased concurrency, caching, and retry logic.

---

## Context

The current pipeline processes rows in 5 strictly sequential phases. Each phase must fully complete before the next begins. At 100K rows this results in an estimated 3-4 hour processing time. The LLM verification phase is the biggest bottleneck — it processes batches of 20 items sequentially with no parallelism.

### Current Architecture

```
[Search ALL rows] → [Verify ALL rows] → [Normalize ALL rows] → [Enrich ALL rows] → [Deliver]
```

### Current Concurrency Settings

| Service | Concurrency | Pattern |
|---------|------------|---------|
| Serper (search) | 20 parallel | asyncio.Semaphore + gather |
| Gemini (verify) | 1 (sequential batches of 20) | Sequential for-loop |
| Normalize | 50 parallel | asyncio.Semaphore + gather |
| QuickEnrich (enrich) | 10 parallel | asyncio.Semaphore + gather |

### Provider Rate Limits (Researched)

| Provider | Rate Limit | Headroom vs Current |
|----------|-----------|-------------------|
| Serper | Up to 300 QPS (tier-dependent) | Massive — currently using 20 |
| Gemini (paid T1) | 150-500 RPM, 1M TPM | Currently sequential — huge room |
| QuickEnrich | 1,000 RPM | Currently 10 concurrent — large room |

### Key Bottlenecks

1. **LLM verification is fully sequential** — single biggest bottleneck
2. **Phases are strictly sequential** — no overlap between phases
3. **No enrichment caching** — only search results are cached
4. **httpx.AsyncClient created per-request in `batch_search()` and `batch_enrich()`** — unnecessary TLS overhead
5. **DB connection pool is 5** — will bottleneck under pipelined load

---

## Design

### 1. Phase Pipelining

**Problem:** All rows must complete Phase N before any row enters Phase N+1.

**Solution:** Use `asyncio.Queue` to pipeline phases. Each phase runs as a long-lived async task that consumes micro-batches from an input queue and pushes completed rows to the next phase's queue.

**Architecture:**

```
                    queue_sv         queue_vn         queue_ne
Chunk 1: [Search] ────────→ [Verify] ────────→ [Normalize] ────────→ [Enrich]
Chunk 2:   [Search] ──────→   [Verify] ──────→   [Normalize] ──────→ [Enrich]
Chunk 3:     [Search] ────→     [Verify] ────→     [Normalize] ────→   ...
                                                                     → [Deliver once all done]
```

**Implementation details:**

- `run_pipeline()` is restructured to launch 4 concurrent async tasks (one per phase: search, verify, normalize, enrich) plus a coordinator
- Each phase task runs a `while True` loop reading from its input `asyncio.Queue`
- A sentinel value (`None`) signals the phase to shut down
- Micro-batch size: 200 rows (configurable via `pipeline_batch_size` setting in `config.py`)
- The search phase queries rows from the DB in micro-batches of `pipeline_batch_size` and pushes them to `queue_sv`
- Each subsequent phase consumes from its input queue, processes, writes results to DB, and pushes to the next queue
- Deliver phase waits for a `completion_event` (asyncio.Event) set when all rows have finished enrichment
- **Queue maxsize: 5** — bounded queues provide backpressure so the fastest phase (search) doesn't outrun slower phases (verify). If a queue is full, the producing phase awaits until the consumer drains an item.

**Data passing between phases:**
- Queues pass **lists of `JobResult` primary keys (UUIDs)** — not ORM objects
- Each phase task queries its own batch of `JobResult` rows from the DB using those keys
- This avoids ORM staleness issues since each phase reads fresh data from the DB

**DB session safety:**
- Each phase task creates and manages **its own `AsyncSession`** via `async with AsyncSessionLocal() as db:`
- The current single-session pattern in `run_pipeline()` is removed — concurrent phases must NOT share a session (SQLAlchemy async sessions are not safe for concurrent use)
- The coordinator task uses its own session for job-level status updates

**Job config propagation:**
- `run_pipeline()` reads the job config (job_titles, max_contacts, enrich_contacts, etc.) once at startup and passes it to the enrich phase task as a plain dict argument (not via the queue)

**Progress tracking:**
- Each phase maintains an `asyncio`-safe counter (simple `int` is fine since we're single-threaded async)
- The coordinator task periodically reads all phase counters and calls `update_job_progress()` with the current phase name and progress

**Error handling:**
- If a row fails in any phase, it's marked with `status="failed"` in the DB and not pushed to the next queue
- If an entire phase task crashes, it sets an `asyncio.Event` (error_event) that causes all other phase tasks to drain and the job to be marked as `"failed"`

**Relationship to existing batch sizes:**
- `pipeline_batch_size` (new, default 200) controls the micro-batch size flowing between queues
- `search_batch_size` (existing, default 100) is removed — replaced by `pipeline_batch_size`
- Intra-phase concurrency is still controlled by the per-service semaphore settings

**Files changed:**
- `backend/app/workers/pipeline.py` — major restructure of `run_pipeline()` and all `phase_*` functions
- `backend/app/config.py` — add `pipeline_batch_size: int = 200`, remove `search_batch_size`

### 2. Parallel LLM Verification

**Problem:** `phase_verify()` processes LLM batches sequentially in a for-loop. Each batch of 20 items waits for the previous batch to complete.

**Solution:** Use the same `asyncio.Semaphore` + `asyncio.gather` pattern already used by search and enrichment. Run up to 5 concurrent LLM batches.

**Implementation details:**

- Add `verify_concurrency: int = 5` to config, replacing the unused `llm_concurrency` setting
- Remove `llm_concurrency` from config to avoid confusion
- In `phase_verify()`, collect items into batches of 20, then dispatch all batches via `asyncio.gather` with a `Semaphore(verify_concurrency)`
- Each batch calls `provider.verify_domains(batch)` independently
- At 5 concurrent batches × 20 items = processing 100 items simultaneously
- Gemini paid T1 supports 150-500 RPM — 5 concurrent batches at ~2-3s each = ~100-150 RPM, safely within even the lower end of the rate limit range
- For users on higher tiers, `verify_concurrency` can be bumped via env var

**Files changed:**
- `backend/app/workers/pipeline.py` — `phase_verify()` restructured
- `backend/app/config.py` — replace `llm_concurrency` with `verify_concurrency`

### 3. Increased Concurrency Limits

**Changes to `config.py` defaults:**

| Setting | Current | New | Rationale |
|---------|---------|-----|-----------|
| `serper_concurrency` | 20 | 50 | Serper supports 300 QPS; 50 is conservative |
| `verify_concurrency` | N/A (replaces `llm_concurrency`) | 5 | Gemini paid T1 = 150-500 RPM; 5 batches safe at lower end |
| `normalize_concurrency` | 50 | 50 | Already good — HTTP HEAD requests are cheap |
| `enrich_concurrency` | 10 | 30 | QuickEnrich supports 1,000 RPM; 30 is conservative |
| `pipeline_batch_size` | N/A (new) | 200 | Micro-batch size for phase pipelining |

All concurrency values remain configurable via environment variables.

**Files changed:**
- `backend/app/config.py`

### 4. Enrichment Caching

**Problem:** QuickEnrich results are never cached. If multiple jobs search for contacts at the same company, each one makes a fresh API call.

**Solution:** Add Redis caching for enrichment results using the same `cache_get`/`cache_set` pattern already used for Serper results.

**Cache key:** `"enrich:{domain}:{sorted_titles}:{max_contacts}"`
- `domain` — normalized domain (lowercase)
- `sorted_titles` — alphabetically sorted, comma-joined, lowercase job titles
- `max_contacts` — integer

**TTL:** 7 days (same as Serper cache, uses existing `cache_ttl_days` setting)

**Implementation details:**
- In `enrich_company()`, check cache before making API call
- On cache miss, make API call and store result
- Cache hit returns stored contacts list immediately

**Files changed:**
- `backend/app/services/enrichment.py` — add cache check/set in `enrich_company()`

### 5. Retry with Exponential Backoff

**Problem:** No retry logic for transient failures (429 rate limits, 5xx server errors) across any service.

**Solution:** Create a shared async retry utility that handles both httpx and SDK-specific exceptions.

**Retry config:**
- `max_retries: 3`
- Base delay: `1.0s`
- Max delay: `15.0s`
- Backoff multiplier: `2.0`
- Jitter: random `0-0.5s` added to each delay
- Retryable status codes (httpx): `429`, `500`, `502`, `503`, `504`

**Implementation:**

```python
async def retry_async(
    fn: Callable,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 15.0,
    retryable_exceptions: tuple[type[Exception], ...] = (),
) -> Any:
    """Retry an async callable with exponential backoff and jitter.

    Handles httpx.HTTPStatusError for retryable status codes,
    plus any additional exception types passed via retryable_exceptions.
    Logs each retry attempt with delay and reason.
    """
    for attempt in range(max_retries + 1):
        try:
            return await fn()
        except httpx.HTTPStatusError as e:
            if e.response.status_code in RETRYABLE_CODES and attempt < max_retries:
                delay = min(base_delay * (2 ** attempt) + random.uniform(0, 0.5), max_delay)
                logger.warning("Retry %d/%d after %s (HTTP %d), delay=%.1fs",
                    attempt + 1, max_retries, type(e).__name__, e.response.status_code, delay)
                await asyncio.sleep(delay)
            else:
                raise
        except retryable_exceptions as e:
            if attempt < max_retries:
                delay = min(base_delay * (2 ** attempt) + random.uniform(0, 0.5), max_delay)
                logger.warning("Retry %d/%d after %s, delay=%.1fs",
                    attempt + 1, max_retries, type(e).__name__, delay)
                await asyncio.sleep(delay)
            else:
                raise
```

**Applied to:**
- `serper.py` — wrap `search_company()` HTTP call
- `enrichment.py` — wrap `enrich_company()` HTTP call
- `gemini.py` — wrap LLM call with `retryable_exceptions=(google.api_core.exceptions.ResourceExhausted, google.api_core.exceptions.ServiceUnavailable)`
- `openai_provider.py` — wrap LLM call with `retryable_exceptions=(openai.RateLimitError, openai.APIStatusError)`
- `normalizer.py` — wrap `resolve_redirect()` HTTP call

**Files changed:**
- `backend/app/services/retry.py` — new file, shared retry utility
- `backend/app/services/serper.py` — wrap HTTP call with retry
- `backend/app/services/enrichment.py` — wrap HTTP call with retry
- `backend/app/services/llm/gemini.py` — wrap LLM call with retry (SDK exceptions)
- `backend/app/services/llm/openai_provider.py` — wrap LLM call with retry (SDK exceptions)
- `backend/app/services/normalizer.py` — wrap HTTP call with retry

### 6. Shared httpx Clients

**Problem:** `batch_search()` (serper.py:105) and `batch_enrich()` (enrichment.py:88) each create a new `httpx.AsyncClient()` per-request inside their semaphore blocks, paying TLS handshake cost every time. Note: the individual service functions (`search_company`, `enrich_company`) already accept a `client` parameter — the issue is in the batch orchestration functions. `batch_normalize()` already creates a single shared client correctly.

**Solution:** Create one shared `httpx.AsyncClient` per batch function with connection pooling, instead of per-request.

**Implementation details:**
- In `batch_search()`, move `httpx.AsyncClient()` creation outside the semaphore/gather loop — create one client and pass it to all concurrent `search_company()` calls
- In `batch_enrich()`, same pattern — one shared client for all concurrent `enrich_company()` calls
- Configure `httpx.Limits(max_connections=concurrency_limit)` on the shared client to match the semaphore size
- `batch_normalize()` already does this correctly — no change needed

**Files changed:**
- `backend/app/services/serper.py` — restructure `batch_search()` client lifecycle
- `backend/app/services/enrichment.py` — restructure `batch_enrich()` client lifecycle

### 7. DB Connection Pool Increase

**Problem:** Pool size of 5 with `max_overflow=0` will bottleneck when pipelined phases run concurrently (4 phase tasks + coordinator + SSE endpoint = 6+ concurrent sessions needed).

**Solution:** Increase pool size to 15 with overflow of 5.

**Files changed:**
- `backend/app/database.py` — update `pool_size=15, max_overflow=5`

---

## Files Changed Summary

| File | Changes |
|------|---------|
| `backend/app/workers/pipeline.py` | Major restructure: queue-based pipelining, per-phase sessions, parallel LLM, shared clients |
| `backend/app/config.py` | New: `verify_concurrency`, `pipeline_batch_size`; remove: `llm_concurrency`, `search_batch_size`; bumped defaults |
| `backend/app/services/retry.py` | **New file** — shared async retry utility with configurable exception types and logging |
| `backend/app/services/serper.py` | Shared httpx client in `batch_search()`, wrap with retry |
| `backend/app/services/enrichment.py` | Add caching, shared httpx client in `batch_enrich()`, wrap with retry |
| `backend/app/services/llm/gemini.py` | Wrap with retry (google SDK exceptions) |
| `backend/app/services/llm/openai_provider.py` | Wrap with retry (openai SDK exceptions) |
| `backend/app/services/normalizer.py` | Wrap with retry |
| `backend/app/database.py` | Bump pool_size to 15, max_overflow to 5 |

---

## Expected Performance Impact

**At 10K rows (estimated):**
| | Current | Optimized |
|---|---|---|
| Total time | ~11 min | ~5-6 min |
| Speedup | — | ~2x |

**At 100K rows (estimated):**
| | Current | Optimized |
|---|---|---|
| Total time | ~3-4 hours | ~30-45 min |
| Speedup | — | ~5-8x |

Primary gains come from:
1. Phase pipelining (~2-3x) — phases overlap instead of waiting
2. Parallel LLM (~2-3x on verify phase) — 5 concurrent batches vs 1
3. Bumped concurrency (~1.5-2x on search/enrich) — more parallel API calls
4. Caching + client reuse (~10-20% on repeated domains) — eliminates redundant work

---

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Gemini rate limits at high concurrency | Default `verify_concurrency=5` is safe for lower T1 limits (150 RPM); configurable via env var for higher tiers |
| Queue memory at 100K rows | Bounded queues (maxsize=5) with backpressure; queues hold only UUID lists, not full ORM objects; each phase re-queries from DB |
| ORM object memory at 100K rows | Micro-batch loading from DB (200 rows at a time per phase) instead of preloading all rows; each phase only holds its current batch in memory |
| Phase crash cascading | Error event propagation shuts down all phases cleanly; job marked as failed |
| DB connection exhaustion | Pool increased to 15+5 overflow; each phase uses its own session |
| Concurrent AsyncSession corruption | Eliminated — each phase task creates its own session; no shared sessions between concurrent tasks |
| Serper credit burn on retries | Retry only on 429/5xx, not on 4xx client errors; cache prevents duplicate searches; failed parse before cache set means retry re-fetches (minor credit cost, acceptable) |
| ARQ job timeout | Current timeout of 7200s (2 hours) is sufficient for optimized 100K processing (~30-45 min). Monitor and adjust if retry storms cause delays. |

---

## Out of Scope

- Multi-worker job splitting (Approach B) — can be added later if needed
- OpenAI Batch API integration — viable future optimization for very large jobs
- Frontend changes — no UI changes needed; SSE progress tracking works as-is
- Database schema changes — no model changes needed
