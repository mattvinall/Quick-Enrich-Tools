# P2 + P3 Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement task-by-task.

**Goal:** Fix verified issues across P2 (QuickEnrich) and P3 (Company Intel) without redesigning architecture. All tasks are surgical and independently shippable.

**Architecture:** Five surgical tasks. Each touches 1-3 files. No shared state between tasks. TDD for every functional change.

**Tech Stack:** Python 3, FastAPI, httpx, asyncio, pytest, pytest-asyncio, Next.js/React.

**Out of scope (intentional):**
- API-key-at-rest encryption (architectural — needs separate design doc)
- SSRF DNS-rebind hardening (TOCTTOU, low-priority, requires httpx event-hook work)
- Token-in-localStorage / SSE-token-in-URL (UX tradeoff — needs product decision)
- Full LLM prompt-injection defense (requires structured-prompt redesign — separate plan)
- Comprehensive P3 test suite (this plan adds one anchor test; fuller coverage is a follow-on)
- Fake index-mismatch bug claimed by reviewers (verified NOT a bug — naming is misleading but code is correct)

---

## Task 1: Add rate limiting to /upload endpoint

**Why:** `email_capture.py:45-46` rate-limits by IP and email, but `upload.py` accepts unlimited 50 MB CSV submissions. A single client can fill the job queue and burn Serper/QuickEnrich credits.

**Files:**
- Modify: `backend/app/routers/upload.py` (apply `check_rate_limit` to IP and email)
- Create: `backend/tests/test_upload_rate_limit.py`

**Steps:**

- [x] **Step 1:** Write failing test in `backend/tests/test_upload_rate_limit.py` that submits `settings.uploads_per_ip_per_day + 1` uploads from the same simulated IP and asserts the last one returns HTTP 429.

- [x] **Step 2:** Add `from app.services.rate_limiter import check_rate_limit` to `upload.py`.

- [x] **Step 3:** Inside the POST handler, after parsing the form and before job creation, call:
```python
ip_address = request.client.host if request.client else "unknown"
await check_rate_limit(db, ip_address, "ip", "upload")
await check_rate_limit(db, body.email, "email", "upload")
```
(Match the `email_capture.py:45-46` pattern exactly.)

- [x] **Step 4:** Add `"upload"` as a valid `action` in `rate_limiter.py` if it's not already permitted. If the current rate_limiter uses a whitelist, extend it.

- [x] **Step 5:** Run tests — both new and full suite — verify green.

- [x] **Step 6:** Commit: `fix(upload): add IP+email rate limiting to /upload endpoint`

---

## Task 2: Sanitize phone and linkedin_url in intel CSV export

**Why:** `backend/app/routers/intel.py:199-205` sanitizes `title/first_name/last_name/email` but passes `phone` and `linkedin_url` through raw. QuickEnrich can return phone strings with `=` prefixes (formatted numbers) that trigger Excel formulas. LinkedIn URL fields can contain similar characters.

**Files:**
- Modify: `backend/app/routers/intel.py:199-205`
- Modify: `backend/app/routers/g2.py` (same pattern exists — check and apply uniformly)
- Add test case to existing test or create `backend/tests/test_intel_csv_export.py`

**Steps:**

- [x] **Step 1:** Grep for `_sanitize_csv` usage across `backend/app/routers/*.py` to find every CSV export site.

- [x] **Step 2:** Write failing test that exports a contact row where `phone = "=cmd|'/C calc'!A0"` and `linkedin_url = "+1-555-MALICIOUS"`, and asserts both cells are prefixed with `'` (or whatever `_sanitize_csv` does) in the resulting CSV.

- [x] **Step 3:** Wrap `phone` and `linkedin_url` in `_sanitize_csv` at `intel.py:203-204`. Apply the same treatment to the G2 router's contact cells where applicable (note: our mobile-field fix from the previous plan left `phone`/`mobile`/`linkedin_url` un-sanitized in `g2.py:217-221` — sanitize those too).

- [x] **Step 4:** Run tests — verify green.

- [x] **Step 5:** Commit: `fix(csv): sanitize phone, mobile, and linkedin_url fields in CSV exports`

---

## Task 3: Fix double-count in intel enrich phase

**Why:** `backend/app/workers/intel_pipeline.py:541` does `total_enriched += len(result_ids)` unconditionally — including when enrichment is skipped (no `quickenrich_api_key`, no `job_titles`, or no eligible domains). The `contacts_enriched` stat in the email + UI stats is inflated.

**Files:**
- Modify: `backend/app/workers/intel_pipeline.py` around line 541
- Update: an existing intel_pipeline test, OR add `backend/tests/test_intel_pipeline_accounting.py`

**Steps:**

- [x] **Step 1:** Read `intel_pipeline.py:450-550` carefully. Identify all branches where `result_ids` pass through the enrich phase without any contact being added.

- [x] **Step 2:** Write failing test: feed the enrich phase a batch where no row has a `normalized_domain` (so enrichment is entirely skipped) and assert `total_enriched` stays at 0.

- [x] **Step 3:** Change the accumulator to only count rows that actually received contacts:
```python
enriched_this_batch = sum(
    1 for r in batch_results if r.status == "enriched"
)
total_enriched += enriched_this_batch
```
Place this after the `await db.commit()` on line 539.

- [x] **Step 4:** Run tests. Run one real job end-to-end locally and confirm the stat in the results email matches reality.

- [x] **Step 5:** Commit: `fix(intel): count only actually-enriched rows in total_enriched`

---

## Task 4: Cap combined page text before sending to LLM

**Why:** `backend/app/services/intel_extractor.py:59-64` concatenates all scraped page text with no length limit. A verbose multi-page site can push a 40KB+ prompt into the LLM, blowing through token budgets silently and creating a larger prompt-injection surface. This is a defensive truncation — not a full prompt-injection fix, but it bounds the blast radius and the cost.

**Files:**
- Modify: `backend/app/services/intel_extractor.py`
- Create: `backend/tests/test_intel_extractor.py`

**Steps:**

- [x] **Step 1:** Add a constant at module top: `_MAX_PROMPT_CHARS = 16000` (approximately 4k tokens, safe for all current providers).

- [x] **Step 2:** Write failing test that passes `pages = ["A" * 20000, "B" * 20000]` to the extractor and asserts the LLM mock is called with a prompt whose combined-text section is `<= _MAX_PROMPT_CHARS`.

- [x] **Step 3:** After building `combined_text` via `"\n\n---\n\n".join(...)`, truncate:
```python
if len(combined_text) > _MAX_PROMPT_CHARS:
    combined_text = combined_text[:_MAX_PROMPT_CHARS] + "\n\n[...truncated]"
    logger.info(
        "intel_extractor: truncated combined page text for %s to %d chars",
        domain, _MAX_PROMPT_CHARS,
    )
```

- [x] **Step 4:** Run tests. Run an end-to-end intel job against a verbose site and confirm the log line fires.

- [x] **Step 5:** Commit: `fix(intel): cap combined page text at 16k chars before LLM call`

---

## Task 5: Mask API key inputs in the frontend

**Why:** `ExtractionSettings.tsx:173-178, 302-307` renders QuickEnrich/Serper/LLM key inputs as `<input type="text">`. Visible in screenshots, screen-shares, demos, and DOM inspectors. Frontend review flagged this as the only critical issue.

**Files:**
- Modify: `frontend/src/components/ExtractionSettings.tsx` (and any sibling component with the same pattern — grep for `api_key` + `type="text"`)

**Steps:**

- [x] **Step 1:** Grep the frontend for inputs that bind to `api_key`, `apiKey`, or known key-field names (`serperApiKey`, `quickenrichApiKey`, `openaiApiKey`, `geminiApiKey`).

- [x] **Step 2:** Change each one's `type="text"` to `type="password"`. Add an optional `autoComplete="off"`.

- [x] **Step 3:** Manual smoke test: open each tool page in dev, confirm keys render as dots and do not echo in screenshots.

- [x] **Step 4:** Commit: `fix(frontend): mask API key inputs with type=password`

---

## Self-Review Notes

**False alarms verified against code (do NOT fix):**
- Index mismatch at `pipeline.py:102`, `pipeline.py:278`, `intel_pipeline.py:144`: `batch_search` / `batch_normalize` emit `row_index` as enumerate position of their INPUT list, and the callers look up by the matching enumerate position. Code is correct — the field name collides with the job-wide `row_index` in JobResult, but the callers never mix them. Leave as-is. (Consider renaming later for clarity in a separate refactor.)

**Deferred (intentionally):**
- API-key encryption at rest (job.config JSONB) — architectural
- Full prompt-injection hardening — needs structured-prompt redesign
- P3 integration test suite — this plan adds one anchor in Task 4; broader coverage follow-up
- SSRF DNS-rebind TOCTTOU fix
- Session-token migration off localStorage

**Execution order:** Tasks 1-5 are independent. Recommended: 2 → 3 → 4 → 1 → 5 (CSV sanitization and accounting first; UX/security polish last).

---

## Execution Handoff

Two options:

**1. Subagent-Driven (recommended)** — fresh subagent per task, review between tasks.

**2. Inline Execution** — execute tasks sequentially with checkpoints.

Which approach?
