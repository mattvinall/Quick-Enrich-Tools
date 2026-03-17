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
4. **httpx.AsyncClient created per-request** — unnecessary TLS overhead
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
- Micro-batch size: 200 rows (configurable via `pipeline_batch_size` setting)
- The search phase reads rows from the DB in micro-batches and pushes them to `queue_sv`
- Each subsequent phase consumes from its input queue, processes, writes results to DB, and pushes to the next queue
- Deliver phase waits for a `completion_event` (asyncio.Event) set when all rows have finished enrichment
- Progress tracking: each phase increments a shared counter; the coordinator periodically calls `update_job_progress()` with the minimum progress across all phases

**Error handling:**
- If a row fails in any phase, it's marked with `status="failed"` and not pushed to the next queue
- If an entire phase task crashes, it sets an error event that causes all other phase tasks to drain and the job to be marked as `"failed"`

**Files changed:**
- `backend/app/workers/pipeline.py` — major restructure of `run_pipeline()` and all `phase_*` functions

### 2. Parallel LLM Verification

**Problem:** `phase_verify()` processes LLM batches sequentially in a for-loop. Each batch of 20 items waits for the previous batch to complete.

**Solution:** Use the same `asyncio.Semaphore` + `asyncio.gather` pattern already used by search and enrichment. Run up to 8 concurrent LLM batches.

**Implementation details:**

- Add `verify_concurrency: int = 8` to config (separate from the existing `llm_concurrency` which was unused)
- In `phase_verify()`, collect items into batches of 20, then dispatch all batches via `asyncio.gather` with a `Semaphore(8)`
- Each batch calls `provider.verify_domains(batch)` independently
- At 8 concurrent batches × 20 items = processing 160 items simultaneously
- Gemini paid T1 supports 150-500 RPM — 8 concurrent batches fits comfortably (each batch = 1 API call)

**Files changed:**
- `backend/app/workers/pipeline.py` — `phase_verify()` restructured
- `backend/app/config.py` — add `verify_concurrency` setting

### 3. Increased Concurrency Limits

**Changes to `config.py` defaults:**

| Setting | Current | New | Rationale |
|---------|---------|-----|-----------|
| `serper_concurrency` | 20 | 50 | Serper supports 300 QPS; 50 is conservative |
| `verify_concurrency` | N/A (new) | 8 | Gemini paid T1 = 150-500 RPM; 8 batches/min is safe |
| `normalize_concurrency` | 50 | 50 | Already good — HTTP HEAD requests are cheap |
| `enrich_concurrency` | 10 | 30 | QuickEnrich supports 1,000 RPM; 30 is conservative |

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

**Solution:** Create a shared async retry utility used by all HTTP-calling services.

**Retry config:**
- `max_retries: 3`
- Base delay: `1.0s`
- Max delay: `15.0s`
- Backoff multiplier: `2.0`
- Jitter: random `0-0.5s` added to each delay
- Retryable status codes: `429`, `500`, `502`, `503`, `504`

**Implementation:**

```python
async def retry_async(fn, max_retries=3, base_delay=1.0, max_delay=15.0):
    for attempt in range(max_retries + 1):
        try:
            return await fn()
        except httpx.HTTPStatusError as e:
            if e.response.status_code in RETRYABLE_CODES and attempt < max_retries:
                delay = min(base_delay * (2 ** attempt) + random.uniform(0, 0.5), max_delay)
                await asyncio.sleep(delay)
            else:
                raise
```

**Applied to:**
- `serper.py` — `search_company()` HTTP call
- `enrichment.py` — `enrich_company()` HTTP call
- `gemini.py` / `openai_provider.py` — LLM API calls
- `normalizer.py` — redirect resolution HTTP HEAD calls

**Files changed:**
- `backend/app/services/retry.py` — new file, shared retry utility
- `backend/app/services/serper.py` — wrap HTTP call with retry
- `backend/app/services/enrichment.py` — wrap HTTP call with retry
- `backend/app/services/llm/gemini.py` — wrap LLM call with retry
- `backend/app/services/llm/openai_provider.py` — wrap LLM call with retry
- `backend/app/services/normalizer.py` — wrap HTTP call with retry

### 6. Shared httpx Clients

**Problem:** Each request creates a new `httpx.AsyncClient()` inside the semaphore block, paying TLS handshake cost every time.

**Solution:** Create one shared `httpx.AsyncClient` per phase with connection pooling. Pass it into the batch functions.

**Implementation details:**
- In pipeline phase functions, create `async with httpx.AsyncClient(timeout=15.0, limits=httpx.Limits(max_connections=concurrency)) as client:` once
- Pass the client into `batch_search()`, `batch_enrich()`, `batch_normalize()`
- Update these functions to accept an optional `client` parameter; if provided, use it instead of creating a new one

**Files changed:**
- `backend/app/workers/pipeline.py` — create clients at phase level
- `backend/app/services/serper.py` — accept optional client parameter
- `backend/app/services/enrichment.py` — accept optional client parameter
- `backend/app/services/normalizer.py` — accept optional client parameter

### 7. DB Connection Pool Increase

**Problem:** Pool size of 5 with `max_overflow=0` will bottleneck when pipelined phases run concurrently.

**Solution:** Increase pool size to 15 with overflow of 5.

**Files changed:**
- `backend/app/database.py` — update `pool_size=15, max_overflow=5`

---

## Files Changed Summary

| File | Changes |
|------|---------|
| `backend/app/workers/pipeline.py` | Major restructure: queue-based pipelining, parallel LLM, shared clients |
| `backend/app/config.py` | New settings: `verify_concurrency`, `pipeline_batch_size`; bumped defaults |
| `backend/app/services/retry.py` | **New file** — shared async retry utility |
| `backend/app/services/serper.py` | Accept shared client, wrap with retry |
| `backend/app/services/enrichment.py` | Add caching, accept shared client, wrap with retry |
| `backend/app/services/llm/gemini.py` | Wrap with retry |
| `backend/app/services/llm/openai_provider.py` | Wrap with retry |
| `backend/app/services/normalizer.py` | Accept shared client, wrap with retry |
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
2. Parallel LLM (~2-3x on verify phase) — 8 concurrent batches vs 1
3. Bumped concurrency (~1.5-2x on search/enrich) — more parallel API calls
4. Caching + client reuse (~10-20% on repeated domains) — eliminates redundant work

---

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Gemini rate limits hit at high concurrency | `verify_concurrency` is configurable; retry with backoff handles 429s |
| Queue memory usage at 100K rows | Micro-batches of 200 rows keep queue depth bounded; rows are DB-backed, not held in memory |
| Phase crash cascading | Error event propagation shuts down all phases cleanly; job marked as failed |
| DB connection exhaustion | Pool increased to 15+5 overflow; monitor with connection pool metrics |
| Serper credit burn on retries | Retry only on 429/5xx, not on 4xx client errors; cache prevents duplicate searches |

---

## Out of Scope

- Multi-worker job splitting (Approach B) — can be added later if needed
- OpenAI Batch API integration — viable future optimization for very large jobs
- Frontend changes — no UI changes needed; SSE progress tracking works as-is
- Database schema changes — no model changes needed
