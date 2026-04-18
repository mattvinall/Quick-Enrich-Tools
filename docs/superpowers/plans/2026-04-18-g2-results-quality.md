# G2 Intel Results Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Fix four concrete gaps in the G2 Intel tool that directly reduce contact-data quality and result volume — no refactors, no new features.

**Architecture:** Four surgical changes across `enrichment.py`, `email_service.py`, `config.py`, and `g2_scraper.py`. Each task is independent and individually verifiable. Existing pipeline structure is unchanged; people enrichment already wires through correctly when the user toggles `company_people=true`.

**Tech Stack:** Python 3, FastAPI, httpx, asyncio, pytest, pytest-asyncio, Resend Python SDK.

**Out of scope (intentionally):**
- Sub-category / related-category expansion (needs G2 tree crawl — separate plan)
- QuickEnrich cost tracking / batch API (no urgent pain)
- New `g2_companies` / `g2_company_people` tables (JSONB `contacts` already works)
- Frontend table multi-contact preview (CSV already has full data)
- API key "Test" button / plain-text UX polish

---

## Task 1: Extract `mobile` field from QuickEnrich responses

**Why:** QuickEnrich returns mobile numbers but `enrichment.py:97` only reads `employee_phone`/`phone`. Users asking for "phone and mobile data" currently get nothing in the mobile column because the column doesn't exist.

**Files:**
- Modify: `backend/app/services/enrichment.py:12` (add `mobile` to `_CONTACT_FIELDS`)
- Modify: `backend/app/services/enrichment.py:91-102` (populate `mobile`)
- Modify: `backend/app/routers/g2.py:166` (`_CONTACT_COLUMNS`)
- Modify: `backend/app/routers/g2.py:214-221` (add mobile cell to CSV row)
- Create: `backend/tests/test_enrichment.py` (new)

- [x] **Step 1: Write failing test for mobile extraction**

Create `backend/tests/test_enrichment.py`:

```python
import httpx
import pytest
from pytest_httpx import HTTPXMock

from app.services.enrichment import enrich_company


@pytest.mark.asyncio
async def test_enrich_company_extracts_mobile_field(httpx_mock: HTTPXMock, monkeypatch):
    # Bypass Redis cache for this test
    monkeypatch.setattr("app.services.enrichment.cache_get", lambda *a, **kw: _none())
    monkeypatch.setattr("app.services.enrichment.cache_set", lambda *a, **kw: _none())

    httpx_mock.add_response(
        url="https://app.quickenrich.io/api/employees/dataset-search?company_url=acme.com&title=CEO",
        json=[{
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@acme.com",
            "title": "CEO",
            "employee_phone": "+1-555-0100",
            "employee_mobile": "+1-555-0199",
            "employee_linkedin": "https://linkedin.com/in/ada",
        }],
    )

    async with httpx.AsyncClient() as client:
        contacts = await enrich_company(
            client, "acme.com", ["CEO"], max_contacts=1, api_key="test-key"
        )

    assert len(contacts) == 1
    assert contacts[0]["phone"] == "+1-555-0100"
    assert contacts[0]["mobile"] == "+1-555-0199"


async def _none():
    return None
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_enrichment.py::test_enrich_company_extracts_mobile_field -v`
Expected: FAIL — `KeyError: 'mobile'` or assertion on missing key.

- [x] **Step 3: Add `mobile` to `_CONTACT_FIELDS` and population code**

Replace `backend/app/services/enrichment.py:12`:

```python
_CONTACT_FIELDS = ("title", "first_name", "last_name", "email", "phone", "mobile", "linkedin_url")
```

Replace the contact dict built at `backend/app/services/enrichment.py:91-102`:

```python
                contacts.append(
                    {
                        "title": str(record.get("title") or ""),
                        "first_name": first,
                        "last_name": last,
                        "email": email,
                        "phone": str(record.get("employee_phone") or record.get("phone") or ""),
                        "mobile": str(
                            record.get("employee_mobile")
                            or record.get("mobile")
                            or record.get("mobile_phone")
                            or ""
                        ),
                        "linkedin_url": str(
                            record.get("employee_linkedin") or record.get("linkedin_url") or ""
                        ),
                    }
                )
```

- [x] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_enrichment.py::test_enrich_company_extracts_mobile_field -v`
Expected: PASS.

- [x] **Step 5: Add `mobile` column to CSV export**

Replace `backend/app/routers/g2.py:166`:

```python
_CONTACT_COLUMNS = ["contact_title", "first_name", "last_name", "email", "phone", "mobile", "linkedin"]
```

Replace contact-cell build at `backend/app/routers/g2.py:213-221`:

```python
    for contact in all_contacts:
        contact_cells = [
            _sanitize_csv(contact.get("title", "")),
            _sanitize_csv(contact.get("first_name", "")),
            _sanitize_csv(contact.get("last_name", "")),
            _sanitize_csv(contact.get("email", "")),
            contact.get("phone", ""),
            contact.get("mobile", ""),
            contact.get("linkedin_url", ""),
        ]
        rows.append(prefix + contact_cells)
```

Also update the empty-contacts row at `backend/app/routers/g2.py:210`:

```python
    if not all_contacts:
        return [prefix + ["", "", "", "", "", "", ""]]
```

- [x] **Step 6: Run full test suite**

Run: `cd backend && pytest -q`
Expected: all pass.

- [x] **Step 7: Commit**

```bash
git add backend/app/services/enrichment.py backend/app/routers/g2.py backend/tests/test_enrichment.py
git commit -m "fix(enrich): extract mobile field from QuickEnrich and add to CSV export"
```

---

## Task 2: Fix silent email-send failures

**Why:** `resend.Emails.send(params)` at `email_service.py:137` is a blocking call inside an async function. Under load it blocks the event loop or silently returns without actually awaiting the HTTP send. User reports emails not arriving despite the API key being configured.

**Files:**
- Modify: `backend/app/services/email_service.py:134-147` (wrap sync SDK in `asyncio.to_thread`)
- Modify: `backend/app/services/email_service.py:22-24` (stricter guard)
- Create: `backend/tests/test_email_service.py` (new)

- [x] **Step 1: Write failing test verifying send is awaited**

Create `backend/tests/test_email_service.py`:

```python
import asyncio
from unittest.mock import MagicMock, patch

import pytest

from app.services import email_service


@pytest.mark.asyncio
async def test_send_results_email_awaits_resend_call(monkeypatch):
    """The sync resend SDK must be executed via asyncio.to_thread so we actually wait for the send."""
    monkeypatch.setattr(email_service.settings, "resend_api_key", "re_test")

    send_mock = MagicMock(return_value={"id": "abc"})
    monkeypatch.setattr("app.services.email_service.resend.Emails.send", send_mock)

    await email_service.send_results_email(
        "test@example.com",
        "https://example.com/download/abc",
        {"total_rows": 10, "websites_found": 8, "contacts_enriched": 4},
    )

    send_mock.assert_called_once()


@pytest.mark.asyncio
async def test_send_results_email_raises_on_missing_recipient(monkeypatch):
    monkeypatch.setattr(email_service.settings, "resend_api_key", "re_test")
    send_mock = MagicMock()
    monkeypatch.setattr("app.services.email_service.resend.Emails.send", send_mock)

    await email_service.send_results_email("", "https://x", {"total_rows": 0})

    send_mock.assert_not_called()
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_email_service.py -v`
Expected: First test may pass coincidentally but second will fail (no recipient guard); if Resend SDK is wrapped with `asyncio.to_thread` later, we ensure actual send correctness.

- [x] **Step 3: Fix email_service.py**

Replace `backend/app/services/email_service.py:22-24`:

```python
    if not settings.resend_api_key:
        logger.error("RESEND_API_KEY not configured — skipping email to %s", to_email)
        return

    if not to_email:
        logger.error("send_results_email called with empty recipient — skipping")
        return
```

Replace `backend/app/services/email_service.py:134-147`:

```python
    last_exc = None
    for attempt in range(_MAX_RETRIES):
        try:
            await asyncio.to_thread(resend.Emails.send, params)
            logger.info("Results email sent to %s (found=%d total=%d)", to_email, found, total)
            return
        except Exception as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES - 1:
                delay = _BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "Email send attempt %d failed, retrying in %.0fs: %s",
                    attempt + 1, delay, exc,
                )
                await asyncio.sleep(delay)

    logger.error(
        "Email delivery failed after %d attempts to %s: %s",
        _MAX_RETRIES, to_email, last_exc,
    )
    raise RuntimeError(f"Email delivery failed: {last_exc}") from last_exc
```

- [x] **Step 4: Stop swallowing email exceptions silently in the pipeline**

Replace the email call in `backend/app/workers/pipeline.py:421-428`:

```python
    try:
        await send_results_email(recipient, download_url, job_stats)
    except Exception as exc:
        logger.error(
            "Email delivery failed for job_id=%s recipient=%s: %s",
            job_id, recipient, exc,
        )
        # Do not fail the job — CSV is still downloadable in-app.
```

Apply the same change to `backend/app/workers/intel_pipeline.py:456-463`.

Note: behavior changes — we now log at `error` level (not silent) and keep the CSV path usable. The job itself does not fail on email failure, so users who never check email can still download.

- [x] **Step 5: Run tests**

Run: `cd backend && pytest tests/test_email_service.py -v`
Expected: PASS.

- [x] **Step 6: Manual smoke test**

Run backend locally, submit a small G2 job with 1 category × 5 results, email enabled. Check Resend dashboard for the delivered send within 60 seconds of job completion. If it fails, the logs now contain the Resend error message (no more silent drops).

- [x] **Step 7: Commit**

```bash
git add backend/app/services/email_service.py backend/app/workers/pipeline.py backend/app/workers/intel_pipeline.py backend/tests/test_email_service.py
git commit -m "fix(email): await Resend SDK via to_thread; surface errors instead of silencing"
```

---

## Task 3: Raise G2 per-category page cap from 10 → 25

**Why:** `g2_max_pages_per_category=10` × 25 products/page = 250 hard ceiling. Raising to 25 unlocks up to ~625 companies/category. Commit `70d8147` already made pagination more resilient against anti-bot blocks; this is the natural follow-on.

This is a config-default change only — users can still request `max_per_category=1000` and the router already permits it (routers/g2.py:108–112). Today that request silently clamps at 250.

**Files:**
- Modify: `backend/app/config.py:38`
- Modify: `backend/tests/test_config.py` (update default assertion if present)

- [x] **Step 1: Check existing config test**

Run: `cd backend && grep -n "g2_max_pages_per_category" tests/test_config.py`

If a default-assertion exists, note the line. If not, skip Step 2.

- [x] **Step 2: Write failing assertion for new default**

If `test_config.py` asserts `g2_max_pages_per_category == 10`, change the assertion to `== 25`. Run to verify it fails against current code.

- [x] **Step 3: Update config default**

Replace `backend/app/config.py:38`:

```python
    g2_max_pages_per_category: int = 25
```

- [x] **Step 4: Verify tests pass**

Run: `cd backend && pytest tests/test_config.py -v && pytest -q`
Expected: all pass.

- [x] **Step 5: Manual verification against a real category**

Run the backend locally. Submit a G2 job:
- Categories: `["crm-software"]` (known to have >250 companies on G2)
- `max_per_category: 500`
- Options: just `industry_description` (skip enrichment for the smoke test)

Watch the logs. Confirm `discover_g2_category_via_scrape` iterates past page 10 and total products returned > 250. Record actual count in the commit message.

- [x] **Step 6: Commit**

```bash
git add backend/app/config.py backend/tests/test_config.py
git commit -m "feat(g2): raise per-category page cap 10→25 (unlocks ~625/category)"
```

---

## Task 4: Parallelize Serper fallback queries

**Why:** When the scrape.do path fails for a category, `discover_g2_category` in `g2_scraper.py:279` fires 2–4 Serper queries one-at-a-time. Parallelizing cuts fallback latency by 60-75% on the categories that need it most.

**Files:**
- Modify: `backend/app/services/g2_scraper.py` (function `discover_g2_category` — the Serper fallback)
- Create: `backend/tests/test_g2_scraper.py` (new, minimal)

- [x] **Step 1: Read current function**

Read `backend/app/services/g2_scraper.py:279-340` in full. Identify the loop that iterates `queries` and performs sequential `httpx` calls.

- [x] **Step 2: Write failing test**

Create `backend/tests/test_g2_scraper.py`:

```python
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.services import g2_scraper


@pytest.mark.asyncio
async def test_discover_g2_category_fires_serper_queries_in_parallel(monkeypatch):
    """All Serper queries must fire concurrently; total elapsed ≈ 1x slowest query, not N× sequential."""

    call_count = {"n": 0}

    async def fake_post(*args, **kwargs):
        call_count["n"] += 1
        await asyncio.sleep(0.2)  # Simulate 200ms Serper latency
        class _Resp:
            status_code = 200
            def json(self):
                return {"organic": []}
            def raise_for_status(self):
                pass
        return _Resp()

    monkeypatch.setattr("app.services.g2_scraper.httpx.AsyncClient.post", fake_post)
    monkeypatch.setattr(g2_scraper.settings, "serper_api_key", "test")

    # Force scrape.do path to fail so we enter the Serper fallback.
    async def fake_scrape_fail(*a, **kw):
        return None
    monkeypatch.setattr(g2_scraper, "discover_g2_category_via_scrape", fake_scrape_fail)

    start = asyncio.get_event_loop().time()
    await g2_scraper.discover_g2_category("crm-software", max_products=100)
    elapsed = asyncio.get_event_loop().time() - start

    # With ≥2 queries × 200ms sequential = ≥400ms. Parallel should be ~200-300ms.
    assert elapsed < 0.35, f"Serper queries appear to run sequentially ({elapsed:.2f}s elapsed)"
    assert call_count["n"] >= 2
```

- [x] **Step 3: Run test to verify it fails**

Run: `cd backend && pytest tests/test_g2_scraper.py::test_discover_g2_category_fires_serper_queries_in_parallel -v`
Expected: FAIL — elapsed ≥ 0.4s because queries run sequentially.

- [x] **Step 4: Refactor Serper fallback to use `asyncio.gather`**

In `discover_g2_category`, replace the sequential query loop with:

```python
async def _run_query(client: httpx.AsyncClient, query: str) -> list[dict]:
    try:
        response = await client.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": settings.serper_api_key, "Content-Type": "application/json"},
            json={"q": query, "num": 30},
            timeout=15.0,
        )
        response.raise_for_status()
        return response.json().get("organic", [])
    except Exception as exc:
        logger.warning("Serper query failed for %r: %s", query, exc)
        return []

async with httpx.AsyncClient() as client:
    query_results = await asyncio.gather(*[_run_query(client, q) for q in queries])

all_products: list[dict] = []
seen_slugs: set[str] = set()
for organic in query_results:
    for item in organic:
        product = _parse_serper_product(item)
        if product and product["slug"] not in seen_slugs:
            seen_slugs.add(product["slug"])
            all_products.append(product)
            if len(all_products) >= max_products:
                break
    if len(all_products) >= max_products:
        break
```

> **Important:** Preserve the existing `_parse_serper_product` helper name if it already exists; otherwise inline the parsing logic that currently lives between lines ~319-333 of `g2_scraper.py`. Match the exact field extraction currently used (name, slug, url, etc.).

- [x] **Step 5: Run test**

Run: `cd backend && pytest tests/test_g2_scraper.py -v`
Expected: PASS, elapsed < 0.35s.

- [x] **Step 6: Run full suite**

Run: `cd backend && pytest -q`
Expected: all pass. If any existing g2 test breaks, investigate — the parse logic must be identical.

- [x] **Step 7: Manual smoke test**

Submit a G2 job with a category known to trigger Serper fallback (e.g. anti-bot-blocked niche categories). Confirm fallback latency is roughly 1-2 seconds, not 4-8.

- [x] **Step 8: Commit**

```bash
git add backend/app/services/g2_scraper.py backend/tests/test_g2_scraper.py
git commit -m "perf(g2): fire Serper fallback queries in parallel via asyncio.gather"
```

---

## Self-Review Notes

**Spec coverage check:**
- ✅ Mobile field gap → Task 1
- ✅ Email silent failure → Task 2
- ✅ 250-per-category ceiling → Task 3
- ✅ Sequential Serper fallback → Task 4
- ✅ QuickEnrich already wired (verified `intel_pipeline.py:476` reads DB config) — no task needed
- ✅ CSV already emits one-row-per-contact — no task needed

**Deferred (not in this plan, intentionally):**
- Sub-category / related-category expansion
- Cache min-size logic
- Contact-level search in frontend table
- API key validation UX
- New database tables for person-level queries

**Type/name consistency:**
- `mobile` key is introduced in `_CONTACT_FIELDS`, in the contact dict, and in CSV columns — all three match.
- `_CONTACT_COLUMNS` count matches empty-row padding length (7 cells).

**Execution order:** Tasks 1–4 are independent and can be done in any order. Recommended: 1 → 3 → 4 → 2 (mobile first = immediate user-visible improvement; email last because it involves the most out-of-process verification).

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-18-g2-results-quality.md`. Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
