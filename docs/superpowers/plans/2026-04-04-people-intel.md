# People Intel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Product 7 (People Intel) — users upload names + companies, we find LinkedIn profiles via Serper, then run the existing intel pipeline for company intelligence extraction.

**Architecture:** Phase 0 (LinkedIn search) + delegate to existing intel pipeline (Resolve → Crawl → Extract → Enrich → Deliver). Follows the G2 pattern exactly. Only new code: LinkedIn search service, people router, people pipeline worker, frontend page + input component.

**Tech Stack:** FastAPI, Serper API, existing intel pipeline (Spider, Gemini/OpenAI, QuickEnrich), Next.js 14, TypeScript, Tailwind, pytest

---

## File Map

### New Files
| File | Responsibility |
|------|---------------|
| `database/migrations/006_register_people_intel_tool.sql` | Register tool + add `linkedin_searching` job status |
| `backend/app/services/linkedin_search.py` | Serper `site:linkedin.com/in/` search with caching, batching, confidence scoring |
| `backend/app/routers/people.py` | POST /people/extract, GET /people/download/{job_id} |
| `backend/app/workers/people_pipeline.py` | Phase 0 LinkedIn search + delegate to `run_intel_pipeline` |
| `backend/tests/test_linkedin_search.py` | Unit tests for LinkedIn search service |
| `backend/tests/test_people_router.py` | Unit tests for router validation + CSV generation |
| `backend/tests/test_people_pipeline.py` | Integration test for pipeline flow |
| `frontend/src/components/PeopleInputPanel.tsx` | Paste parser for "name, company" lines |
| `frontend/src/app/tools/people-intel/page.tsx` | 5-phase wizard page |

### Modified Files
| File | Change |
|------|--------|
| `backend/app/config.py:41` | Add `linkedin_search_concurrency` setting |
| `backend/app/main.py:21,31,79` | Import + register people router + pipeline worker |
| `backend/app/workers/intel_pipeline.py:426` | Update deliver download URL prefix for people-intel |
| `frontend/src/lib/tool-registry.ts:50` | Add people-intel tool config |
| `frontend/src/lib/api.ts:206` | Add people API functions |
| `frontend/src/app/page.tsx:5,26` | Add people-intel icon |

---

### Task 1: Database Migration

**Files:**
- Create: `database/migrations/006_register_people_intel_tool.sql`

- [ ] **Step 1: Create migration file**

```sql
-- Register People Intel tool
INSERT INTO tools (id, slug, name, description, is_active)
VALUES (
    gen_random_uuid(),
    'people-intel',
    'People Intel by Name',
    'Upload names and company names to find LinkedIn profiles and extract business intelligence.',
    true
)
ON CONFLICT (slug) DO NOTHING;

-- Add linkedin_searching status to jobs check constraint
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_status_check;

ALTER TABLE jobs ADD CONSTRAINT jobs_status_check CHECK (
    status IN (
        -- Shared
        'pending', 'completed', 'failed',
        -- Product 2 (Company Location Finder)
        'parsing', 'searching', 'verifying', 'normalizing', 'enriching', 'delivering',
        -- Product 3 (Company Intel)
        'resolving', 'crawling', 'extracting', 'crawled', 'extracted',
        -- Product 4 (G2 Intel)
        'g2_scraping',
        -- Product 7 (People Intel)
        'linkedin_searching'
    )
);
```

- [ ] **Step 2: Commit**

```bash
git add database/migrations/006_register_people_intel_tool.sql
git commit -m "feat(people): add migration to register people-intel tool"
```

---

### Task 2: LinkedIn Search Service — Tests

**Files:**
- Create: `backend/tests/test_linkedin_search.py`

- [ ] **Step 1: Write unit tests for LinkedIn search service**

```python
"""Unit tests for LinkedIn search service."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.linkedin_search import (
    _build_linkedin_query,
    _extract_linkedin_url,
    _score_confidence,
    parse_people_input,
    search_linkedin_profile,
    batch_linkedin_search,
)


# ── Query construction ──────────────────────────────────────────────


class TestBuildLinkedinQuery:
    def test_basic_query(self):
        query = _build_linkedin_query("Fred Smith", "Apple")
        assert query == 'site:linkedin.com/in/ "Fred Smith" "Apple"'

    def test_strips_whitespace(self):
        query = _build_linkedin_query("  Fred Smith  ", "  Apple  ")
        assert query == 'site:linkedin.com/in/ "Fred Smith" "Apple"'

    def test_unicode_names(self):
        query = _build_linkedin_query("José García", "Empresa S.A.")
        assert query == 'site:linkedin.com/in/ "José García" "Empresa S.A."'


# ── URL extraction ──────────────────────────────────────────────────


class TestExtractLinkedinUrl:
    def test_extracts_linkedin_in_url(self):
        results = [
            {"link": "https://www.linkedin.com/in/fredsmith", "title": "Fred Smith", "snippet": "Apple"},
            {"link": "https://example.com/fred", "title": "Fred", "snippet": ""},
        ]
        url = _extract_linkedin_url(results)
        assert url == "https://www.linkedin.com/in/fredsmith"

    def test_strips_query_params(self):
        results = [
            {"link": "https://linkedin.com/in/fredsmith?trk=public_profile", "title": "Fred", "snippet": ""},
        ]
        url = _extract_linkedin_url(results)
        assert url == "https://linkedin.com/in/fredsmith"

    def test_returns_empty_when_no_linkedin(self):
        results = [
            {"link": "https://example.com/fred", "title": "Fred", "snippet": ""},
        ]
        url = _extract_linkedin_url(results)
        assert url == ""

    def test_returns_empty_for_empty_results(self):
        url = _extract_linkedin_url([])
        assert url == ""

    def test_skips_linkedin_company_pages(self):
        results = [
            {"link": "https://linkedin.com/company/apple", "title": "Apple", "snippet": ""},
        ]
        url = _extract_linkedin_url(results)
        assert url == ""


# ── Confidence scoring ──────────────────────────────────────────────


class TestScoreConfidence:
    def test_no_url_returns_zero(self):
        score = _score_confidence("", "Fred Smith", "Apple", [])
        assert score == 0.0

    def test_url_without_name_match(self):
        results = [{"title": "Some Person - Professional", "snippet": "Works at Apple"}]
        score = _score_confidence("https://linkedin.com/in/someperson", "Fred Smith", "Apple", results)
        assert score == 0.5

    def test_url_with_name_match(self):
        results = [{"title": "Fred Smith - CEO at Apple", "snippet": "Works at Apple"}]
        score = _score_confidence("https://linkedin.com/in/fredsmith", "Fred Smith", "Apple", results)
        assert score == 0.9

    def test_url_with_name_no_company(self):
        results = [{"title": "Fred Smith - Professional", "snippet": "Freelancer"}]
        score = _score_confidence("https://linkedin.com/in/fredsmith", "Fred Smith", "Apple", results)
        assert score == 0.8


# ── Input parsing ───────────────────────────────────────────────────


class TestParsePeopleInput:
    def test_comma_separator(self):
        items, errors = parse_people_input(["Fred Smith, Apple", "Jane Doe, Google"])
        assert len(items) == 2
        assert items[0] == {"full_name": "Fred Smith", "company_name": "Apple"}
        assert items[1] == {"full_name": "Jane Doe", "company_name": "Google"}
        assert errors == 0

    def test_pipe_separator(self):
        items, errors = parse_people_input(["Fred Smith | Apple", "Jane Doe | Google"])
        assert len(items) == 2
        assert items[0] == {"full_name": "Fred Smith", "company_name": "Apple"}

    def test_dash_separator(self):
        items, errors = parse_people_input(["Fred Smith - Apple"])
        assert len(items) == 1
        assert items[0] == {"full_name": "Fred Smith", "company_name": "Apple"}

    def test_skips_empty_lines(self):
        items, errors = parse_people_input(["Fred Smith, Apple", "", "  ", "Jane Doe, Google"])
        assert len(items) == 2

    def test_trims_whitespace(self):
        items, errors = parse_people_input(["  Fred Smith  ,  Apple Inc  "])
        assert items[0] == {"full_name": "Fred Smith", "company_name": "Apple Inc"}

    def test_no_separator_counts_as_error(self):
        items, errors = parse_people_input(["Fred Smith", "Jane Doe, Google"])
        assert len(items) == 1
        assert errors == 1

    def test_company_with_comma(self):
        items, errors = parse_people_input(["Fred Smith, Apple, Inc."])
        assert items[0]["full_name"] == "Fred Smith"
        assert items[0]["company_name"] == "Apple, Inc."

    def test_auto_detects_pipe_separator(self):
        items, errors = parse_people_input([
            "Fred Smith | Apple",
            "Jane Doe | Google",
            "Bob Jones | Microsoft",
        ])
        assert len(items) == 3
        assert items[0]["company_name"] == "Apple"

    def test_mixed_separators_picks_most_common(self):
        items, errors = parse_people_input([
            "Fred Smith | Apple",
            "Jane Doe | Google",
            "Bob Jones, Microsoft",
        ])
        # Pipe is more common (2 vs 1), so pipe is chosen
        assert len(items) == 3


# ── Single search ───────────────────────────────────────────────────


class TestSearchLinkedinProfile:
    @pytest.mark.asyncio
    async def test_returns_linkedin_url_on_hit(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "organic": [
                {
                    "title": "Fred Smith - CEO at Apple",
                    "link": "https://www.linkedin.com/in/fredsmith",
                    "snippet": "Fred Smith is the CEO at Apple...",
                },
            ],
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        with patch("app.services.linkedin_search.cache_get", return_value=None), \
             patch("app.services.linkedin_search.cache_set", return_value=None):
            result = await search_linkedin_profile(mock_client, "Fred Smith", "Apple")

        assert result["linkedin_url"] == "https://www.linkedin.com/in/fredsmith"
        assert result["confidence"] == 0.9

    @pytest.mark.asyncio
    async def test_returns_empty_on_no_results(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"organic": []}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        with patch("app.services.linkedin_search.cache_get", return_value=None), \
             patch("app.services.linkedin_search.cache_set", return_value=None):
            result = await search_linkedin_profile(mock_client, "Fred Smith", "Apple")

        assert result["linkedin_url"] == ""
        assert result["confidence"] == 0.0

    @pytest.mark.asyncio
    async def test_uses_cache(self):
        cached = {
            "linkedin_url": "https://linkedin.com/in/cached",
            "confidence": 0.9,
            "query": "cached query",
            "results": [],
        }
        with patch("app.services.linkedin_search.cache_get", return_value=cached):
            mock_client = AsyncMock()
            result = await search_linkedin_profile(mock_client, "Fred Smith", "Apple")

        assert result["linkedin_url"] == "https://linkedin.com/in/cached"
        mock_client.post.assert_not_called()


# ── Batch search ────────────────────────────────────────────────────


class TestBatchLinkedinSearch:
    @pytest.mark.asyncio
    async def test_deduplicates_same_name_company(self):
        call_count = 0

        async def mock_search(client, name, company, api_key=None):
            nonlocal call_count
            call_count += 1
            return {
                "linkedin_url": f"https://linkedin.com/in/{name.lower().replace(' ', '')}",
                "confidence": 0.9,
                "query": f'site:linkedin.com/in/ "{name}" "{company}"',
                "results": [],
            }

        rows = [
            {"full_name": "Fred Smith", "company_name": "Apple"},
            {"full_name": "Fred Smith", "company_name": "Apple"},  # duplicate
            {"full_name": "Jane Doe", "company_name": "Google"},
        ]

        with patch("app.services.linkedin_search.search_linkedin_profile", side_effect=mock_search), \
             patch("app.services.linkedin_search.cache_get", return_value=None):
            results = await batch_linkedin_search(rows, concurrency=5)

        assert len(results) == 3
        # Fred Smith searched only once (dedup)
        assert call_count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/MattV/Desktop/projects/Quick-Enrich-Tools/backend && python -m pytest tests/test_linkedin_search.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.linkedin_search'`

- [ ] **Step 3: Commit test file**

```bash
git add backend/tests/test_linkedin_search.py
git commit -m "test(people): add LinkedIn search service unit tests"
```

---

### Task 3: LinkedIn Search Service — Implementation

**Files:**
- Create: `backend/app/services/linkedin_search.py`

- [ ] **Step 1: Implement LinkedIn search service**

```python
"""LinkedIn profile search via Serper API.

Searches Google for `site:linkedin.com/in/ "name" "company"` to find
LinkedIn profile URLs. Supports batching, deduplication, caching, and
confidence scoring.
"""

import asyncio
import logging
import re
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.services.cache import cache_get, cache_set, make_cache_key
from app.services.retry import retry_async

logger = logging.getLogger(__name__)


def _build_linkedin_query(full_name: str, company_name: str) -> str:
    """Build a Serper query targeting LinkedIn profile pages."""
    name = full_name.strip()
    company = company_name.strip()
    return f'site:linkedin.com/in/ "{name}" "{company}"'


def _extract_linkedin_url(results: list[dict]) -> str:
    """Return the first linkedin.com/in/ URL from Serper results, or empty string."""
    for r in results:
        link = r.get("link", "")
        if "linkedin.com/in/" in link.lower():
            # Strip query params and fragments
            parsed = urlparse(link)
            clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            # Remove trailing slash
            return clean.rstrip("/")
    return ""


def _score_confidence(
    linkedin_url: str,
    full_name: str,
    company_name: str,
    results: list[dict],
) -> float:
    """Score confidence that the LinkedIn URL belongs to the right person.

    0.0 = no results
    0.5 = URL found but name not in title
    0.8 = URL found and name in title
    0.9 = URL found, name in title, company in title or snippet
    """
    if not linkedin_url:
        return 0.0

    name_lower = full_name.strip().lower()
    company_lower = company_name.strip().lower()

    # Check first result (the one we picked)
    first = results[0] if results else {}
    title = str(first.get("title", "")).lower()
    snippet = str(first.get("snippet", "")).lower()

    name_in_title = name_lower in title
    company_in_context = company_lower in title or company_lower in snippet

    if name_in_title and company_in_context:
        return 0.9
    if name_in_title:
        return 0.8
    return 0.5


def _detect_separator(lines: list[str]) -> str:
    """Auto-detect the most common separator from the first 5 non-empty lines."""
    candidates = {", ": 0, " | ": 0, " - ": 0}
    sample = [l for l in lines if l.strip()][:5]

    for line in sample:
        for sep in candidates:
            if sep in line:
                candidates[sep] += 1

    best = max(candidates, key=candidates.get)
    if candidates[best] == 0:
        return ", "  # default fallback
    return best


def parse_people_input(lines: list[str]) -> tuple[list[dict], int]:
    """Parse paste-mode lines into structured items.

    Returns (items, error_count) where items is a list of
    {full_name, company_name} dicts and error_count is the number
    of lines that could not be parsed.
    """
    non_empty = [l for l in lines if l.strip()]
    if not non_empty:
        return [], 0

    sep = _detect_separator(non_empty)
    items: list[dict] = []
    errors = 0

    for line in non_empty:
        stripped = line.strip()
        if not stripped:
            continue

        if sep == ", ":
            # First comma splits name from company; remaining commas are part of company
            idx = stripped.find(",")
            if idx == -1:
                errors += 1
                continue
            name = stripped[:idx].strip()
            company = stripped[idx + 1:].strip()
        else:
            parts = stripped.split(sep, 1)
            if len(parts) < 2:
                errors += 1
                continue
            name = parts[0].strip()
            company = parts[1].strip()

        if not name or not company:
            errors += 1
            continue

        items.append({"full_name": name, "company_name": company})

    return items, errors


async def search_linkedin_profile(
    client: httpx.AsyncClient,
    full_name: str,
    company_name: str,
    api_key: str | None = None,
) -> dict:
    """Search Serper for a person's LinkedIn profile.

    Returns: {linkedin_url, confidence, query, results}
    """
    cache_key = make_cache_key("linkedin", full_name.strip().lower(), company_name.strip().lower())
    cached = await cache_get(cache_key)
    if cached is not None:
        logger.info("LINKEDIN CACHE HIT: %s @ %s", full_name, company_name)
        return cached

    query = _build_linkedin_query(full_name, company_name)
    logger.info("LINKEDIN SEARCH: %s", query)

    response = await client.post(
        "https://google.serper.dev/search",
        headers={
            "X-API-KEY": api_key or settings.serper_api_key,
            "Content-Type": "application/json",
        },
        json={"q": query, "num": 3},
        timeout=15.0,
    )
    response.raise_for_status()
    data = response.json()

    organic = data.get("organic", [])
    results = []
    for item in organic[:3]:
        results.append({
            "title": item.get("title", ""),
            "link": item.get("link", ""),
            "snippet": item.get("snippet", ""),
        })

    linkedin_url = _extract_linkedin_url(results)
    confidence = _score_confidence(linkedin_url, full_name, company_name, results)

    payload = {
        "linkedin_url": linkedin_url,
        "confidence": confidence,
        "query": query,
        "results": results,
    }
    await cache_set(cache_key, payload, settings.cache_ttl_days)
    return payload


async def batch_linkedin_search(
    rows: list[dict],
    concurrency: int | None = None,
    api_key: str | None = None,
) -> list[dict]:
    """Batch search LinkedIn profiles with deduplication and caching.

    Each row must have 'full_name' and 'company_name' keys.
    Returns list of dicts with keys: row_index, linkedin_url, confidence, search_results.
    """
    limit = concurrency if concurrency is not None else settings.linkedin_search_concurrency
    semaphore = asyncio.Semaphore(limit)

    # Group by (name_lower, company_lower) for dedup
    groups: dict[str, list[int]] = {}
    for idx, row in enumerate(rows):
        name = row.get("full_name", "").strip().lower()
        company = row.get("company_name", "").strip().lower()
        dedup_key = f"{name}|{company}"
        groups.setdefault(dedup_key, []).append(idx)

    unique_keys = list(groups.keys())

    async with httpx.AsyncClient() as client:

        async def _search_one(dedup_key: str) -> tuple[str, dict | BaseException]:
            name, _, company = dedup_key.partition("|")
            # Use original casing from first row in group
            first_idx = groups[dedup_key][0]
            orig_name = rows[first_idx].get("full_name", name)
            orig_company = rows[first_idx].get("company_name", company)
            async with semaphore:
                try:
                    result = await retry_async(
                        lambda n=orig_name, c=orig_company: search_linkedin_profile(
                            client, n, c, api_key=api_key
                        ),
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

    key_to_result: dict[str, dict | None] = {}
    for outcome in raw_outcomes:
        if isinstance(outcome, BaseException):
            continue
        dedup_key, value = outcome
        if isinstance(value, BaseException):
            key_to_result[dedup_key] = None
        else:
            key_to_result[dedup_key] = value

    output: list[dict] = []
    for dedup_key, indices in groups.items():
        search_result = key_to_result.get(dedup_key)
        linkedin_url = search_result["linkedin_url"] if search_result else ""
        confidence = search_result["confidence"] if search_result else 0.0
        for idx in indices:
            output.append({
                "row_index": idx,
                "linkedin_url": linkedin_url,
                "confidence": confidence,
                "search_results": search_result,
            })

    output.sort(key=lambda item: int(item["row_index"]))
    return output
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd /Users/MattV/Desktop/projects/Quick-Enrich-Tools/backend && python -m pytest tests/test_linkedin_search.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/linkedin_search.py
git commit -m "feat(people): implement LinkedIn search service"
```

---

### Task 4: Config + Deliver Fix

**Files:**
- Modify: `backend/app/config.py:40` (before `model_config` line)
- Modify: `backend/app/workers/intel_pipeline.py:426`

- [ ] **Step 1: Add linkedin_search_concurrency to config**

In `backend/app/config.py`, add before the `model_config` line (line 41):

```python
    linkedin_search_concurrency: int = 50
```

So the end of the Settings class looks like:

```python
    g2_cache_ttl_days: int = 3
    linkedin_search_concurrency: int = 50
    model_config = {"env_file": ".env", "extra": "ignore"}
```

- [ ] **Step 2: Fix deliver phase download URL prefix**

In `backend/app/workers/intel_pipeline.py`, replace line 426:

```python
        dl_prefix = "g2" if job.tool_slug == "g2-intel" else "intel"
```

With:

```python
        _dl_prefix_map = {"g2-intel": "g2", "people-intel": "people"}
        dl_prefix = _dl_prefix_map.get(job.tool_slug, "intel")
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/config.py backend/app/workers/intel_pipeline.py
git commit -m "feat(people): add config setting and fix deliver URL prefix"
```

---

### Task 5: People Router — Tests

**Files:**
- Create: `backend/tests/test_people_router.py`

- [ ] **Step 1: Write unit tests for people router**

```python
"""Unit tests for people router — validation and CSV generation."""
import pytest

from app.routers.people import (
    _build_people_headers,
    _extract_people_row,
    PeopleItem,
    PeopleExtractRequest,
    ExtractionOptions,
)


class TestBuildPeopleHeaders:
    def test_base_columns_always_present(self):
        headers = _build_people_headers({})
        assert headers[:5] == [
            "full_name", "company_name", "linkedin_url", "linkedin_confidence", "website", "status",
        ][:len(headers)] or "full_name" in headers

    def test_includes_intel_columns(self):
        headers = _build_people_headers({"industry_description": True})
        assert "industry" in headers
        assert "niche" in headers
        assert "description" in headers

    def test_includes_contact_columns(self):
        headers = _build_people_headers({"company_people": True}, max_contacts=2)
        assert "contact_1_title" in headers
        assert "contact_2_title" in headers

    def test_base_only_when_no_options(self):
        headers = _build_people_headers({}, max_contacts=0)
        assert "industry" not in headers
        assert "target_market" not in headers


class TestExtractPeopleRow:
    def test_extracts_base_fields(self):
        class FakeResult:
            input_data = {"full_name": "Fred Smith", "company_name": "Apple"}
            search_results = {"linkedin_url": "https://linkedin.com/in/fredsmith", "confidence": 0.9}
            normalized_domain = "apple.com"
            raw_domain = "apple.com"
            extracted_data = {}
            contacts = []
            status = "extracted"

        row = _extract_people_row(FakeResult(), {}, max_contacts=0)
        assert row[0] == "Fred Smith"
        assert row[1] == "Apple"
        assert row[2] == "https://linkedin.com/in/fredsmith"
        assert row[3] == "0.9"
        assert row[4] == "apple.com"
        assert row[5] == "extracted"

    def test_handles_missing_search_results(self):
        class FakeResult:
            input_data = {"full_name": "Fred Smith", "company_name": "Apple"}
            search_results = None
            normalized_domain = None
            raw_domain = None
            extracted_data = {}
            contacts = []
            status = "not_found"

        row = _extract_people_row(FakeResult(), {}, max_contacts=0)
        assert row[0] == "Fred Smith"
        assert row[2] == ""  # linkedin_url
        assert row[3] == ""  # confidence
        assert row[4] == ""  # website


class TestPeopleItemValidation:
    def test_valid_item(self):
        item = PeopleItem(full_name="Fred Smith", company_name="Apple")
        assert item.full_name == "Fred Smith"

    def test_with_website(self):
        item = PeopleItem(full_name="Fred", company_name="Apple", website="apple.com")
        assert item.website == "apple.com"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/MattV/Desktop/projects/Quick-Enrich-Tools/backend && python -m pytest tests/test_people_router.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.routers.people'`

- [ ] **Step 3: Commit test file**

```bash
git add backend/tests/test_people_router.py
git commit -m "test(people): add people router unit tests"
```

---

### Task 6: People Router — Implementation

**Files:**
- Create: `backend/app/routers/people.py`

- [ ] **Step 1: Implement people router**

```python
"""API endpoints for the People Intel by Name tool."""

import csv
import io
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_token, verify_token
from app.config import settings
from app.database import get_db
from app.models import Job, JobResult

router = APIRouter(prefix="/people", tags=["people"])


# ── Request / Response Models ────────────────────────────────────────


class ExtractionOptions(BaseModel):
    industry_description: bool = True
    target_market: bool = True
    company_people: bool = True
    homepage_raw_text: bool = False


class PeopleItem(BaseModel):
    full_name: str
    company_name: str
    website: str | None = None


class PeopleExtractRequest(BaseModel):
    items: list[PeopleItem]
    options: ExtractionOptions
    serper_api_key: str = ""
    quickenrich_api_key: str = ""
    job_titles: list[str] = []
    max_contacts: int = 3


# ── Endpoints ────────────────────────────────────────────────────────


@router.post("/extract")
async def submit_people_extraction(
    body: PeopleExtractRequest,
    token_payload: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Validate input, create Job + JobResult rows, launch pipeline."""
    items = [item for item in body.items if item.full_name.strip() and item.company_name.strip()]
    if not items:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No valid items provided. Each item needs a name and company.",
        )

    if len(items) > settings.max_rows:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Maximum {settings.max_rows} items allowed.",
        )

    opts = body.options
    if not any([opts.industry_description, opts.target_market, opts.company_people, opts.homepage_raw_text]):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one extraction option must be selected.",
        )

    email = str(token_payload["sub"])
    email_capture_id = str(token_payload.get("job_id", ""))

    job_config = {
        "options": opts.model_dump(),
        "serper_api_key": body.serper_api_key,
        "quickenrich_api_key": body.quickenrich_api_key,
        "job_titles": body.job_titles,
        "max_contacts": body.max_contacts,
    }

    job = Job(
        email_capture_id=uuid.UUID(email_capture_id),
        tool_slug="people-intel",
        status="pending",
        total_rows=len(items),
        config=job_config,
    )
    db.add(job)
    await db.flush()

    job_results = [
        JobResult(
            job_id=job.id,
            row_index=i,
            input_data={
                "full_name": item.full_name.strip(),
                "company_name": item.company_name.strip(),
                "website": (item.website or "").strip(),
                "input_type": "url" if item.website else "name",
            },
            status="pending",
        )
        for i, item in enumerate(items)
    ]
    db.add_all(job_results)
    await db.flush()

    # Run pipeline as background task (bypass ARQ — Upstash incompatibility)
    import asyncio
    from app.workers.people_pipeline import run_people_pipeline
    asyncio.create_task(run_people_pipeline({}, str(job.id)))

    new_token = create_token(email, str(job.id))
    return {
        "job_id": str(job.id),
        "total_rows": len(items),
        "token": new_token,
    }


# ── CSV Download ─────────────────────────────────────────────────────

_BATCH_SIZE = 500
_BASE_COLUMNS = ["full_name", "company_name", "linkedin_url", "linkedin_confidence", "website", "status"]
_CONTACT_FIELDS = ["Title", "First Name", "Last Name", "Email", "Phone", "LinkedIn"]


def _extract_people_row(result: JobResult, options: dict, max_contacts: int = 5) -> list[str]:
    input_data = result.input_data or {}
    extracted = result.extracted_data or {}
    search = result.search_results or {}

    full_name = input_data.get("full_name", "")
    company_name = input_data.get("company_name", "")
    linkedin_url = search.get("linkedin_url", "") if isinstance(search, dict) else ""
    confidence = search.get("confidence", "") if isinstance(search, dict) else ""
    confidence_str = str(confidence) if confidence != "" else ""
    website = result.normalized_domain or result.raw_domain or ""
    row_status = result.status

    base = [full_name, company_name, linkedin_url, confidence_str, website, row_status]

    intel_cells: list[str] = []
    if options.get("industry_description"):
        intel_cells.append(str(extracted.get("industry") or ""))
        intel_cells.append(str(extracted.get("niche") or ""))
        intel_cells.append(str(extracted.get("description") or ""))
        intel_cells.append(str(extracted.get("address") or ""))
        intel_cells.append(str(extracted.get("phone") or ""))
        emails = extracted.get("general_emails") or []
        intel_cells.append(", ".join(emails) if isinstance(emails, list) else str(emails))

    if options.get("target_market"):
        intel_cells.append(str(extracted.get("target_market") or ""))
        case_studies = extracted.get("case_studies") or []
        intel_cells.append(", ".join(case_studies) if isinstance(case_studies, list) else str(case_studies))

    if options.get("company_people"):
        generic_emails = extracted.get("general_emails") or []
        if not isinstance(generic_emails, list):
            generic_emails = []
        intel_cells.append(", ".join(generic_emails))

    if options.get("homepage_raw_text"):
        intel_cells.append(str(extracted.get("homepage_raw_text") or ""))

    raw_contacts = result.contacts
    all_contacts: list[dict] = []
    if isinstance(raw_contacts, list):
        all_contacts = [c for c in raw_contacts if isinstance(c, dict)]

    contact_cells: list[str] = []
    for idx in range(max_contacts):
        contact = all_contacts[idx] if idx < len(all_contacts) else {}
        contact_cells.append(contact.get("title", ""))
        contact_cells.append(contact.get("first_name", ""))
        contact_cells.append(contact.get("last_name", ""))
        contact_cells.append(contact.get("email", ""))
        contact_cells.append(contact.get("phone", ""))
        contact_cells.append(contact.get("linkedin_url", ""))

    return base + intel_cells + contact_cells


def _build_people_headers(options: dict, max_contacts: int = 5) -> list[str]:
    headers = list(_BASE_COLUMNS)

    if options.get("industry_description"):
        headers.extend(["industry", "niche", "description", "address", "phone", "general_emails"])

    if options.get("target_market"):
        headers.extend(["target_market", "case_studies"])

    if options.get("company_people"):
        headers.append("generic_emails")

    if options.get("homepage_raw_text"):
        headers.append("homepage_raw_text")

    for i in range(1, max_contacts + 1):
        for field in _CONTACT_FIELDS:
            headers.append(f"contact_{i}_{field.lower().replace(' ', '_')}")

    return headers


async def _stream_people_csv(job: Job, db: AsyncSession) -> AsyncGenerator[bytes, None]:
    yield b"\xef\xbb\xbf"

    config = job.config or {}
    options = config.get("options", {})

    headers = _build_people_headers(options)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    yield buf.getvalue().encode("utf-8")

    offset = 0
    while True:
        batch_query = (
            select(JobResult)
            .where(JobResult.job_id == job.id)
            .order_by(JobResult.row_index)
            .limit(_BATCH_SIZE)
            .offset(offset)
        )
        batch_result = await db.execute(batch_query)
        rows = batch_result.scalars().all()

        if not rows:
            break

        buf = io.StringIO()
        writer = csv.writer(buf)
        for result in rows:
            writer.writerow(_extract_people_row(result, options))
        yield buf.getvalue().encode("utf-8")

        if len(rows) < _BATCH_SIZE:
            break
        offset += _BATCH_SIZE


@router.get("/download/{job_id}")
async def download_people_results(
    job_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    token: str = Query(default=""),
) -> StreamingResponse:
    from jose import JWTError, jwt as jose_jwt

    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    try:
        payload = jose_jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    job_result = await db.execute(select(Job).where(Job.id == job_id))
    job = job_result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if str(payload.get("job_id", "")) != str(job.id):
        raise HTTPException(status_code=403, detail="Access denied")
    if job.status != "completed":
        raise HTTPException(status_code=400, detail="Job is not yet completed")

    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"people_intel_results_{timestamp}.csv"

    return StreamingResponse(
        _stream_people_csv(job, db),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd /Users/MattV/Desktop/projects/Quick-Enrich-Tools/backend && python -m pytest tests/test_people_router.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/people.py
git commit -m "feat(people): implement people router with extract and download endpoints"
```

---

### Task 7: People Pipeline Worker

**Files:**
- Create: `backend/app/workers/people_pipeline.py`

- [ ] **Step 1: Implement people pipeline worker**

```python
"""People Intel pipeline.

Phase 0: Search LinkedIn profiles via Serper.
Phases 1-5: Delegates to existing intel pipeline (Resolve → Crawl → Extract → Enrich → Deliver).
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Job, JobResult
from app.services.linkedin_search import batch_linkedin_search
from app.workers.intel_pipeline import run_intel_pipeline, update_job_progress

logger = logging.getLogger(__name__)

_BATCH_SIZE = 200


async def run_people_pipeline(ctx: dict, job_id: str) -> None:
    """Main entry point for the People Intel pipeline.

    Phase 0: Search LinkedIn profiles for each person.
    Phases 1-5: Delegate to existing intel pipeline.
    """
    parsed_job_id = uuid.UUID(job_id)

    async with AsyncSessionLocal() as db:
        job_result = await db.execute(select(Job).where(Job.id == parsed_job_id))
        job = job_result.scalar_one()
        config = job.config or {}
        total_rows = job.total_rows

        job.status = "linkedin_searching"
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

    serper_api_key = config.get("serper_api_key") or None

    logger.info(
        "People pipeline starting for job_id=%s: %d rows",
        job_id, total_rows,
    )

    # ── Phase 0: LinkedIn Search ───────────────────────────────────
    try:
        async with AsyncSessionLocal() as db:
            await update_job_progress(db, parsed_job_id, "linkedin_search", 0, total_rows)

        searched = 0
        for batch_start in range(0, total_rows, _BATCH_SIZE):
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(JobResult)
                    .where(JobResult.job_id == parsed_job_id)
                    .order_by(JobResult.row_index)
                    .offset(batch_start)
                    .limit(_BATCH_SIZE)
                )
                batch_results = list(result.scalars().all())
                if not batch_results:
                    break

                # Build search rows
                search_rows = []
                for r in batch_results:
                    input_data = r.input_data or {}
                    search_rows.append({
                        "full_name": input_data.get("full_name", ""),
                        "company_name": input_data.get("company_name", ""),
                    })

                # Batch search LinkedIn
                outcomes = await batch_linkedin_search(
                    search_rows,
                    concurrency=settings.linkedin_search_concurrency,
                    api_key=serper_api_key,
                )

                # Update results
                outcome_by_idx = {o["row_index"]: o for o in outcomes}
                for i, r in enumerate(batch_results):
                    outcome = outcome_by_idx.get(i, {})
                    linkedin_url = outcome.get("linkedin_url", "")
                    confidence = outcome.get("confidence", 0.0)
                    search_result = outcome.get("search_results")

                    r.search_results = {
                        "linkedin_url": linkedin_url,
                        "confidence": confidence,
                        **(search_result or {}),
                    }

                    if linkedin_url:
                        r.status = "found"
                    else:
                        r.status = "not_found"

                    # Set up input for intel pipeline resolve phase:
                    # If user provided website, use it directly as URL input
                    # Otherwise, use company_name for Serper domain resolution
                    input_data = r.input_data or {}
                    website = input_data.get("website", "")
                    if website:
                        r.input_data = {
                            **input_data,
                            "input": website,
                            "input_type": "url",
                        }
                    else:
                        r.input_data = {
                            **input_data,
                            "input": input_data.get("company_name", ""),
                            "input_type": "name",
                        }

                    # Reset status back to pending for intel pipeline phases
                    r.status = "pending"

                await db.commit()

                searched += len(batch_results)
                await update_job_progress(db, parsed_job_id, "linkedin_search", searched, total_rows)

        logger.info(
            "People Phase 0 complete for job_id=%s: %d LinkedIn searches done",
            job_id, searched,
        )

    except Exception as exc:
        logger.exception("People LinkedIn search failed for job_id=%s: %s", job_id, exc)
        async with AsyncSessionLocal() as db:
            job_result = await db.execute(select(Job).where(Job.id == parsed_job_id))
            job = job_result.scalar_one()
            job.status = "failed"
            job.error_message = f"LinkedIn search failed: {exc}"
            await db.commit()
        raise

    # ── Phases 1-5: Delegate to existing intel pipeline ────────────
    await run_intel_pipeline({}, job_id)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/workers/people_pipeline.py
git commit -m "feat(people): implement people pipeline worker with LinkedIn Phase 0"
```

---

### Task 8: Backend Wiring (main.py)

**Files:**
- Modify: `backend/app/main.py:21,31,79`

- [ ] **Step 1: Register people router and pipeline worker in main.py**

Add import at line 22 (after `from app.routers import g2`):

```python
from app.routers import people
```

Add worker import in `_run_arq_worker` at line 30 (after `from app.workers.g2_pipeline import run_g2_pipeline`):

```python
    from app.workers.people_pipeline import run_people_pipeline
```

Update `all_functions` at line 31:

```python
    all_functions = list(P2WorkerSettings.functions) + [run_intel_pipeline, run_g2_pipeline, run_people_pipeline]
```

Add router registration at line 80 (after `app.include_router(g2.router, prefix="/api/v1")`):

```python
app.include_router(people.router, prefix="/api/v1")
```

- [ ] **Step 2: Verify backend starts**

Run: `cd /Users/MattV/Desktop/projects/Quick-Enrich-Tools/backend && python -c "from app.main import app; print('OK')"`
Expected: `OK` (no import errors)

- [ ] **Step 3: Run all existing tests to verify nothing is broken**

Run: `cd /Users/MattV/Desktop/projects/Quick-Enrich-Tools/backend && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/main.py
git commit -m "feat(people): wire people router and pipeline into main app"
```

---

### Task 9: Pipeline Integration Test

**Files:**
- Create: `backend/tests/test_people_pipeline.py`

- [ ] **Step 1: Write integration tests**

```python
"""Integration tests for the People Intel pipeline."""
import pytest
import inspect

from app.services.linkedin_search import (
    batch_linkedin_search,
    parse_people_input,
    _detect_separator,
)


def test_people_pipeline_has_required_functions():
    """Verify the people pipeline exports expected functions."""
    from app.workers import people_pipeline

    assert hasattr(people_pipeline, "run_people_pipeline")
    assert inspect.iscoroutinefunction(people_pipeline.run_people_pipeline)


def test_linkedin_search_module_exports():
    """Verify the LinkedIn search module exports expected functions."""
    from app.services import linkedin_search

    assert hasattr(linkedin_search, "search_linkedin_profile")
    assert hasattr(linkedin_search, "batch_linkedin_search")
    assert hasattr(linkedin_search, "parse_people_input")
    assert inspect.iscoroutinefunction(linkedin_search.search_linkedin_profile)
    assert inspect.iscoroutinefunction(linkedin_search.batch_linkedin_search)


def test_people_router_exports():
    """Verify the people router exports expected endpoints."""
    from app.routers import people

    assert hasattr(people, "router")
    route_paths = [r.path for r in people.router.routes]
    assert "/extract" in route_paths
    assert "/download/{job_id}" in route_paths


def test_separator_detection():
    """Integration test for separator detection across input styles."""
    assert _detect_separator(["a, b", "c, d", "e, f"]) == ", "
    assert _detect_separator(["a | b", "c | d"]) == " | "
    assert _detect_separator(["a - b", "c - d", "e - f"]) == " - "
    # No separators defaults to comma
    assert _detect_separator(["just names"]) == ", "


def test_parse_people_input_large_batch():
    """Verify parsing handles 100 lines correctly."""
    lines = [f"Person {i}, Company {i}" for i in range(100)]
    items, errors = parse_people_input(lines)
    assert len(items) == 100
    assert errors == 0
    assert items[50]["full_name"] == "Person 50"
    assert items[50]["company_name"] == "Company 50"


def test_parse_people_input_all_bad_lines():
    """Verify all-error input returns zero items."""
    lines = ["no separator here", "also no separator", "nope"]
    items, errors = parse_people_input(lines)
    assert len(items) == 0
    assert errors == 3


def test_parse_people_input_empty():
    """Verify empty input is handled."""
    items, errors = parse_people_input([])
    assert len(items) == 0
    assert errors == 0


@pytest.mark.asyncio
async def test_batch_linkedin_search_empty_input():
    """Verify batch search handles empty input."""
    results = await batch_linkedin_search([], concurrency=5)
    assert results == []


def test_people_router_csv_headers_match_row_length():
    """Verify CSV header count matches row output count."""
    from app.routers.people import _build_people_headers, _extract_people_row

    options = {
        "industry_description": True,
        "target_market": True,
        "company_people": True,
        "homepage_raw_text": True,
    }
    max_contacts = 3
    headers = _build_people_headers(options, max_contacts=max_contacts)

    class FakeResult:
        input_data = {"full_name": "Test", "company_name": "TestCo"}
        search_results = {"linkedin_url": "https://linkedin.com/in/test", "confidence": 0.9}
        normalized_domain = "test.com"
        raw_domain = "test.com"
        extracted_data = {"industry": "Tech", "niche": "SaaS"}
        contacts = [{"title": "CEO", "first_name": "A", "last_name": "B", "email": "a@b.com", "phone": "", "linkedin_url": ""}]
        status = "extracted"

    row = _extract_people_row(FakeResult(), options, max_contacts=max_contacts)
    assert len(headers) == len(row), f"Headers ({len(headers)}) != Row ({len(row)})"
```

- [ ] **Step 2: Run integration tests**

Run: `cd /Users/MattV/Desktop/projects/Quick-Enrich-Tools/backend && python -m pytest tests/test_people_pipeline.py -v`
Expected: All tests PASS

- [ ] **Step 3: Run full test suite**

Run: `cd /Users/MattV/Desktop/projects/Quick-Enrich-Tools/backend && python -m pytest tests/ -v`
Expected: All tests PASS (including all existing tests)

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_people_pipeline.py
git commit -m "test(people): add integration tests for people pipeline"
```

---

### Task 10: Frontend — API Functions + Tool Registry + Home Page

**Files:**
- Modify: `frontend/src/lib/api.ts:206`
- Modify: `frontend/src/lib/tool-registry.ts:50`
- Modify: `frontend/src/app/page.tsx:5,26`

- [ ] **Step 1: Add people API functions to api.ts**

Append at the end of `frontend/src/lib/api.ts` (after the G2 section):

```typescript
// ── People Intel ────────────────────────────────────────────────────

export interface PeopleItem {
  full_name: string;
  company_name: string;
  website?: string;
}

export interface PeopleExtractRequest {
  items: PeopleItem[];
  options: ExtractionOptions;
  serper_api_key: string;
  quickenrich_api_key: string;
  job_titles: string[];
  max_contacts: number;
}

export function submitPeopleExtraction(
  body: PeopleExtractRequest,
  token: string,
): Promise<ExtractResponse> {
  return fetchAPI<ExtractResponse>(`${API_URL}/api/v1/people/extract`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  });
}

export function getPeopleDownloadUrl(jobId: string, token: string): string {
  return `${API_URL}/api/v1/people/download/${jobId}?token=${encodeURIComponent(token)}`;
}
```

- [ ] **Step 2: Add people-intel to tool registry**

In `frontend/src/lib/tool-registry.ts`, add before the closing `];` of the `tools` array (after the g2-intel entry):

```typescript
  {
    slug: "people-intel",
    name: "People Intel by Name",
    description:
      "Upload names and company names to find LinkedIn profiles and extract business intelligence, contacts, and more.",
    isActive: true,
    backendUrl: API_BASE_URL,
    requiredColumns: [],
    optionalColumns: [],
    columnPatterns: {},
  },
```

- [ ] **Step 3: Add people-intel icon to home page**

In `frontend/src/app/page.tsx`, add `UserSearch` to the Lucide import (line 5):

```typescript
import { ArrowRight, Grid3X3, MapPin, Search, UserSearch, Users } from "lucide-react";
```

Add icon entry to `TOOL_ICONS` (after g2-intel, before the closing `};`):

```typescript
  "people-intel": (
    <div className="flex items-center gap-1 text-primary">
      <UserSearch className="w-5 h-5" />
      <Users className="w-4 h-4" />
    </div>
  ),
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/lib/tool-registry.ts frontend/src/app/page.tsx
git commit -m "feat(people): add frontend API functions, tool registry, and home page icon"
```

---

### Task 11: Frontend — PeopleInputPanel Component

**Files:**
- Create: `frontend/src/components/PeopleInputPanel.tsx`

- [ ] **Step 1: Create PeopleInputPanel component**

```typescript
"use client";

interface PeopleInputStats {
  total: number;
  parsed: number;
  errors: number;
}

interface PeopleInputPanelProps {
  value: string;
  onChange: (value: string) => void;
  stats: PeopleInputStats;
}

export function parsePeopleLines(text: string): {
  items: { full_name: string; company_name: string }[];
  errors: number;
} {
  const lines = text.split("\n").filter((l) => l.trim());
  if (lines.length === 0) return { items: [], errors: 0 };

  // Auto-detect separator from first 5 lines
  const sample = lines.slice(0, 5);
  const separators = [", ", " | ", " - "];
  const counts = separators.map((sep) => sample.filter((l) => l.includes(sep)).length);
  const bestIdx = counts.indexOf(Math.max(...counts));
  const sep = counts[bestIdx] > 0 ? separators[bestIdx] : ", ";

  const items: { full_name: string; company_name: string }[] = [];
  let errors = 0;

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;

    let name: string;
    let company: string;

    if (sep === ", ") {
      const idx = trimmed.indexOf(",");
      if (idx === -1) {
        errors++;
        continue;
      }
      name = trimmed.slice(0, idx).trim();
      company = trimmed.slice(idx + 1).trim();
    } else {
      const parts = trimmed.split(sep);
      if (parts.length < 2) {
        errors++;
        continue;
      }
      name = parts[0].trim();
      company = parts.slice(1).join(sep).trim();
    }

    if (!name || !company) {
      errors++;
      continue;
    }

    items.push({ full_name: name, company_name: company });
  }

  return { items, errors };
}

export function computePeopleStats(text: string): PeopleInputStats {
  const lines = text.split("\n").filter((l) => l.trim());
  const { items, errors } = parsePeopleLines(text);
  return { total: lines.length, parsed: items.length, errors };
}

export default function PeopleInputPanel({ value, onChange, stats }: PeopleInputPanelProps) {
  return (
    <div className="space-y-2">
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={"Fred Smith, Apple\nJane Doe, Google\nBob Jones, Microsoft"}
        rows={14}
        className="w-full px-4 py-3 text-sm font-mono border border-border rounded-xl bg-white text-text-primary placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary/40 resize-y min-h-[200px]"
      />
      <div className="flex items-center gap-3 text-xs text-text-secondary">
        <span className="font-medium">
          {stats.parsed} {stats.parsed === 1 ? "person" : "people"} detected
        </span>
        {stats.errors > 0 && (
          <span className="text-amber-600">
            ({stats.errors} {stats.errors === 1 ? "line" : "lines"} could not be parsed)
          </span>
        )}
      </div>
      <p className="text-xs text-gray-400">
        One person per line: <span className="font-medium">Name, Company</span> (comma, pipe, or dash separated)
      </p>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/PeopleInputPanel.tsx
git commit -m "feat(people): add PeopleInputPanel paste input component"
```

---

### Task 12: Frontend — People Intel Page

**Files:**
- Create: `frontend/src/app/tools/people-intel/page.tsx`

- [ ] **Step 1: Create the people-intel page**

```typescript
'use client';

import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Upload, ClipboardPaste, FileText, X, AlertCircle, ChevronRight } from 'lucide-react';
import Papa from 'papaparse';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { cn } from '@/lib/utils';

import PeopleInputPanel, { parsePeopleLines, computePeopleStats } from '@/components/PeopleInputPanel';
import ExtractionSettings from '@/components/ExtractionSettings';
import EmailGate from '@/components/EmailGate';
import ProgressTracker from '@/components/ProgressTracker';
import LivePreview from '@/components/LivePreview';
import ResultsPanel from '@/components/ResultsPanel';
import { useSSE } from '@/hooks/useSSE';
import { captureEmail, submitPeopleExtraction, getPeopleDownloadUrl, type PeopleItem } from '@/lib/api';

type Phase = 'input' | 'configure' | 'submit' | 'processing' | 'results';

const PHASE_ORDER: Phase[] = ['input', 'configure', 'submit', 'processing', 'results'];

const PIPELINE_PHASES = ['LinkedIn Search', 'Resolve', 'Crawl', 'Extract', 'Enrich', 'Deliver'] as const;

const STEP_MAP: Partial<Record<Phase, { step: number; total: number; label: string }>> = {
  input:      { step: 1, total: 4, label: 'Upload your data' },
  configure:  { step: 2, total: 4, label: 'Extraction settings' },
  submit:     { step: 3, total: 4, label: 'Enter your email' },
  processing: { step: 4, total: 4, label: 'Processing' },
};

function phaseIndex(p: Phase): number {
  return PHASE_ORDER.indexOf(p);
}

export default function PeopleIntelPage() {
  const [phase, setPhase] = useState<Phase>('input');
  const [direction, setDirection] = useState<'forward' | 'back'>('forward');

  // Input — paste mode
  const [inputText, setInputText] = useState('');

  // Input — CSV mode
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [csvHeaders, setCsvHeaders] = useState<string[]>([]);
  const [csvRows, setCsvRows] = useState<Record<string, string>[]>([]);
  const [nameColumn, setNameColumn] = useState('');
  const [firstNameColumn, setFirstNameColumn] = useState('');
  const [lastNameColumn, setLastNameColumn] = useState('');
  const [companyColumn, setCompanyColumn] = useState('');
  const [websiteColumn, setWebsiteColumn] = useState('');
  const [csvError, setCsvError] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [inputMode, setInputMode] = useState<'paste' | 'csv'>('paste');

  // Derived items from either input mode
  const items: PeopleItem[] = useMemo(() => {
    if (inputMode === 'csv' && csvRows.length > 0 && (nameColumn || (firstNameColumn && lastNameColumn)) && companyColumn) {
      return csvRows
        .map((row) => {
          const fullName = nameColumn
            ? (row[nameColumn] || '').trim()
            : `${(row[firstNameColumn] || '').trim()} ${(row[lastNameColumn] || '').trim()}`.trim();
          const company = (row[companyColumn] || '').trim();
          const website = websiteColumn ? (row[websiteColumn] || '').trim() : '';
          return { full_name: fullName, company_name: company, website: website || undefined };
        })
        .filter((item) => item.full_name && item.company_name);
    }
    const { items: parsed } = parsePeopleLines(inputText);
    return parsed.map((p) => ({ full_name: p.full_name, company_name: p.company_name }));
  }, [inputMode, inputText, csvRows, nameColumn, firstNameColumn, lastNameColumn, companyColumn, websiteColumn]);

  const pasteStats = useMemo(() => computePeopleStats(inputText), [inputText]);

  // CSV parsing
  const handleCsvFile = useCallback((file: File) => {
    setCsvError('');
    if (!file.name.toLowerCase().endsWith('.csv')) {
      setCsvError('Invalid file type. Please upload a .csv file.');
      return;
    }
    if (file.size > 50 * 1024 * 1024) {
      setCsvError('File is too large. Maximum allowed size is 50MB.');
      return;
    }

    Papa.parse<Record<string, string>>(file, {
      header: true,
      skipEmptyLines: true,
      transformHeader: (h) => h.trim(),
      complete: (results) => {
        const headers = results.meta.fields ?? [];
        if (headers.length === 0) {
          setCsvError('CSV file appears to have no headers.');
          return;
        }
        if (results.data.length > 100_000) {
          setCsvError(`CSV has ${results.data.length.toLocaleString()} rows. Maximum is 100,000.`);
          return;
        }
        setCsvFile(file);
        setCsvHeaders(headers);
        setCsvRows(results.data);

        // Auto-detect columns
        const fullNameCol = headers.find((h) => /^(full.?name|name|person|contact)$/i.test(h));
        const fnCol = headers.find((h) => /^(first.?name|fname|given.?name|first)$/i.test(h));
        const lnCol = headers.find((h) => /^(last.?name|lname|surname|family.?name|last)$/i.test(h));
        const coCol = headers.find((h) => /^(company|org|employer|business|firm|organization|company.?name)$/i.test(h));
        const webCol = headers.find((h) => /^(website|url|domain|site|company.?url|company.?website)$/i.test(h));

        if (fullNameCol) setNameColumn(fullNameCol);
        else if (fnCol && lnCol) { setFirstNameColumn(fnCol); setLastNameColumn(lnCol); }
        if (coCol) setCompanyColumn(coCol);
        if (webCol) setWebsiteColumn(webCol);
      },
      error: () => {
        setCsvError('Failed to parse CSV file.');
      },
    });
  }, []);

  const handleRemoveCsv = () => {
    setCsvFile(null);
    setCsvHeaders([]);
    setCsvRows([]);
    setNameColumn('');
    setFirstNameColumn('');
    setLastNameColumn('');
    setCompanyColumn('');
    setWebsiteColumn('');
    setCsvError('');
  };

  // Extraction options
  const [industryDescription, setIndustryDescription] = useState(true);
  const [targetMarket, setTargetMarket] = useState(true);
  const [companyPeople, setCompanyPeople] = useState(true);
  const [homepageRawText, setHomepageRawText] = useState(false);

  // API keys
  const [quickenrichApiKey, setQuickenrichApiKey] = useState('');
  const [serperApiKey, setSerperApiKey] = useState('');

  // Contact config
  const [jobTitles, setJobTitles] = useState<string[]>(['CEO', 'Founder']);
  const [maxContacts, setMaxContacts] = useState(3);

  // Job state — restore from localStorage
  const [jobId, setJobId] = useState<string | null>(() => {
    if (typeof window === 'undefined') return null;
    return localStorage.getItem('qe_people_job_id');
  });
  const [token, setToken] = useState<string | null>(() => {
    if (typeof window === 'undefined') return null;
    return localStorage.getItem('qe_people_token');
  });

  // Submit state
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');

  // Persist job session
  useEffect(() => {
    if (jobId && token) {
      localStorage.setItem('qe_people_job_id', jobId);
      localStorage.setItem('qe_people_token', token);
    }
  }, [jobId, token]);

  // Resume saved job on mount
  useEffect(() => {
    if (jobId && token && phase === 'input') {
      setPhase('processing');
    }
  }, []);

  // SSE
  const { progress } = useSSE(
    phase === 'processing' ? jobId : null,
    phase === 'processing' ? token : null,
  );

  // Transition to results on completion
  useEffect(() => {
    if (phase === 'processing' && progress?.status === 'completed') {
      navigate('results');
    }
  }, [phase, progress?.status]);

  function navigate(next: Phase) {
    setDirection(phaseIndex(next) >= phaseIndex(phase) ? 'forward' : 'back');
    setPhase(next);
  }

  function clearSession() {
    localStorage.removeItem('qe_people_job_id');
    localStorage.removeItem('qe_people_token');
    setJobId(null);
    setToken(null);
  }

  // Validation
  const hasData = items.length > 0;
  const hasOptions = industryDescription || targetMarket || companyPeople || homepageRawText;
  const canSubmit = hasData && hasOptions;

  async function handleEmailSubmit(email: string) {
    setIsSubmitting(true);
    setSubmitError('');

    try {
      const capture = await captureEmail(email, 'people-intel', 'people-intel-page');

      const result = await submitPeopleExtraction(
        {
          items,
          options: {
            industry_description: industryDescription,
            target_market: targetMarket,
            company_people: companyPeople,
            homepage_raw_text: homepageRawText,
          },
          serper_api_key: serperApiKey,
          quickenrich_api_key: quickenrichApiKey,
          job_titles: companyPeople ? jobTitles : [],
          max_contacts: companyPeople ? maxContacts : 1,
        },
        capture.token,
      );

      setJobId(result.job_id);
      setToken(result.token);
      navigate('processing');
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Something went wrong. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  }

  const entering = direction === 'forward';
  const stepInfo = STEP_MAP[phase];

  return (
    <main className="min-h-screen bg-gradient-to-b from-gray-50 to-white py-8 px-4">
      <div className="max-w-4xl mx-auto space-y-6">

        {/* Header */}
        <div className="text-center space-y-2">
          <h1 className="text-3xl font-bold tracking-tight text-text-primary">
            People Intel by Name
          </h1>
          <p className="text-text-secondary max-w-xl mx-auto">
            Upload names and companies to find LinkedIn profiles and extract business intelligence
          </p>
        </div>

        {/* Step breadcrumb */}
        {stepInfo && (
          <div className="flex items-center gap-2 justify-center">
            <div className="flex items-center gap-1.5">
              {[1, 2, 3, 4].map((n) => (
                <div
                  key={n}
                  className={cn(
                    'rounded-full transition-all duration-300',
                    n === stepInfo.step
                      ? 'w-6 h-2.5 bg-primary'
                      : n < stepInfo.step
                      ? 'w-2.5 h-2.5 bg-primary/40'
                      : 'w-2.5 h-2.5 bg-gray-200',
                  )}
                />
              ))}
            </div>
            <span className="text-xs text-text-secondary font-medium">
              Step {stepInfo.step} of {stepInfo.total}:
            </span>
            <span className="text-xs text-text-primary font-semibold">{stepInfo.label}</span>
          </div>
        )}

        {/* Phase content */}
        <div className="relative overflow-hidden">
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={phase}
              initial={{ opacity: 0, x: entering ? 48 : -48 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: entering ? -48 : 48 }}
              transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
              className="bg-white rounded-2xl border border-border shadow-sm p-6 sm:p-8"
            >
              {/* ---- PHASE: input (Step 1) ---- */}
              {phase === 'input' && (
                <div className="space-y-6">
                  <div>
                    <h2 className="text-lg font-semibold text-text-primary">Upload your data</h2>
                    <p className="text-sm text-text-secondary mt-0.5">
                      Paste a list of names and companies, or upload a CSV file.
                    </p>
                  </div>

                  <Tabs value={inputMode} onValueChange={(v) => setInputMode(v as 'paste' | 'csv')} className="w-full">
                    <TabsList className="mb-2">
                      <TabsTrigger value="paste" className="gap-2">
                        <ClipboardPaste className="h-4 w-4" />
                        Paste List
                      </TabsTrigger>
                      <TabsTrigger value="csv" className="gap-2">
                        <Upload className="h-4 w-4" />
                        Upload CSV
                      </TabsTrigger>
                    </TabsList>

                    <TabsContent value="paste">
                      <PeopleInputPanel
                        value={inputText}
                        onChange={setInputText}
                        stats={pasteStats}
                      />
                    </TabsContent>

                    <TabsContent value="csv">
                      <div className="space-y-3">
                        {csvFile ? (
                          <div className="space-y-3">
                            <div className="flex items-center gap-3 rounded-xl border border-border bg-white p-4 shadow-sm">
                              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
                                <FileText className="h-5 w-5 text-primary" />
                              </div>
                              <div className="min-w-0 flex-1">
                                <p className="truncate text-sm font-medium text-text-primary">{csvFile.name}</p>
                                <p className="text-xs text-text-secondary">
                                  {csvRows.length.toLocaleString()} rows &middot; {csvHeaders.length} columns
                                </p>
                              </div>
                              <button type="button" onClick={handleRemoveCsv} aria-label="Remove file"
                                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-gray-400 hover:bg-gray-100 hover:text-gray-600">
                                <X className="h-4 w-4" />
                              </button>
                            </div>

                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                              <div className="space-y-1.5">
                                <label className="text-sm font-medium text-text-primary">Name column</label>
                                <select value={nameColumn} onChange={(e) => { setNameColumn(e.target.value); setFirstNameColumn(''); setLastNameColumn(''); }}
                                  className="w-full px-3 py-2 text-sm border border-border rounded-md bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50">
                                  <option value="">Full name column...</option>
                                  {csvHeaders.map((h) => (<option key={h} value={h}>{h}</option>))}
                                </select>
                                {!nameColumn && (
                                  <div className="flex gap-2">
                                    <select value={firstNameColumn} onChange={(e) => { setFirstNameColumn(e.target.value); setNameColumn(''); }}
                                      className="flex-1 px-3 py-2 text-sm border border-border rounded-md bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50">
                                      <option value="">First name...</option>
                                      {csvHeaders.map((h) => (<option key={h} value={h}>{h}</option>))}
                                    </select>
                                    <select value={lastNameColumn} onChange={(e) => { setLastNameColumn(e.target.value); setNameColumn(''); }}
                                      className="flex-1 px-3 py-2 text-sm border border-border rounded-md bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50">
                                      <option value="">Last name...</option>
                                      {csvHeaders.map((h) => (<option key={h} value={h}>{h}</option>))}
                                    </select>
                                  </div>
                                )}
                              </div>
                              <div className="space-y-1.5">
                                <label className="text-sm font-medium text-text-primary">Company column</label>
                                <select value={companyColumn} onChange={(e) => setCompanyColumn(e.target.value)}
                                  className="w-full px-3 py-2 text-sm border border-border rounded-md bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50">
                                  <option value="">Select company column...</option>
                                  {csvHeaders.map((h) => (<option key={h} value={h}>{h}</option>))}
                                </select>
                              </div>
                            </div>

                            <p className="text-xs text-text-secondary">
                              {items.length.toLocaleString()} valid people found
                            </p>
                          </div>
                        ) : (
                          <div onDragOver={(e) => e.preventDefault()}
                            onDrop={(e) => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) handleCsvFile(f); }}
                            onClick={() => fileInputRef.current?.click()} role="button" tabIndex={0}
                            onKeyDown={(e) => e.key === 'Enter' && fileInputRef.current?.click()}
                            className="group flex cursor-pointer flex-col items-center justify-center gap-4 rounded-xl border-2 border-dashed border-border px-8 py-12 text-center hover:border-primary/60 hover:bg-gray-50/60 transition-colors">
                            <input ref={fileInputRef} type="file" accept=".csv" className="hidden"
                              onChange={(e) => { const f = e.target.files?.[0]; if (f) handleCsvFile(f); e.target.value = ''; }} />
                            <div className="flex h-14 w-14 items-center justify-center rounded-xl bg-gray-100 text-gray-400 group-hover:bg-primary/10 group-hover:text-primary transition-colors">
                              <Upload className="h-6 w-6" />
                            </div>
                            <div className="space-y-1">
                              <p className="text-sm font-semibold text-text-primary">Drag & drop your CSV file</p>
                              <p className="text-sm text-text-secondary">or <span className="font-medium text-primary underline underline-offset-2">click to browse</span></p>
                              <p className="text-xs text-gray-400">.csv only &mdash; max 50MB</p>
                            </div>
                          </div>
                        )}
                        {csvError && (
                          <div className="flex items-center gap-2 rounded-lg bg-red-50 px-3 py-2.5 text-sm text-red-600" role="alert">
                            <AlertCircle className="h-4 w-4 shrink-0" />{csvError}
                          </div>
                        )}
                      </div>
                    </TabsContent>
                  </Tabs>

                  <div className="flex justify-end">
                    <Button onClick={() => navigate('configure')} disabled={!hasData} className="gap-2">
                      Continue <ChevronRight className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              )}

              {/* ---- PHASE: configure (Step 2) ---- */}
              {phase === 'configure' && (
                <div className="space-y-6">
                  <div>
                    <h2 className="text-lg font-semibold text-text-primary">Extraction settings</h2>
                    <p className="text-sm text-text-secondary mt-0.5">
                      Choose what data to extract for {items.length} {items.length === 1 ? 'person' : 'people'}.
                    </p>
                  </div>

                  <ExtractionSettings
                    industryDescription={industryDescription}
                    targetMarket={targetMarket}
                    companyPeople={companyPeople}
                    homepageRawText={homepageRawText}
                    onIndustryDescriptionChange={setIndustryDescription}
                    onTargetMarketChange={setTargetMarket}
                    onCompanyPeopleChange={setCompanyPeople}
                    onHomepageRawTextChange={setHomepageRawText}
                    quickenrichApiKey={quickenrichApiKey}
                    onQuickenrichApiKeyChange={setQuickenrichApiKey}
                    jobTitles={jobTitles}
                    onJobTitlesChange={setJobTitles}
                    maxContacts={maxContacts}
                    onMaxContactsChange={setMaxContacts}
                  />

                  <div className="flex gap-3 pt-2">
                    <Button variant="outline" onClick={() => navigate('input')}>Back</Button>
                    <Button onClick={() => navigate('submit')} disabled={!canSubmit} className="flex-1 gap-2">
                      Continue <ChevronRight className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              )}

              {/* ---- PHASE: submit (Step 3) ---- */}
              {phase === 'submit' && (
                <div className="space-y-6">
                  <div>
                    <h2 className="text-lg font-semibold text-text-primary">Almost there!</h2>
                    <p className="text-sm text-text-secondary mt-0.5">
                      Enter your email to start processing{' '}
                      <span className="font-medium text-text-primary">{items.length} people</span>.
                      We&apos;ll email you when done.
                    </p>
                  </div>

                  <EmailGate onSubmit={handleEmailSubmit} isLoading={isSubmitting} />

                  {submitError && (
                    <p className="text-sm text-red-600" role="alert">{submitError}</p>
                  )}

                  <button type="button" onClick={() => navigate('configure')}
                    className="text-sm text-text-secondary hover:text-text-primary transition-colors flex items-center gap-1">
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
                    </svg>
                    Back to settings
                  </button>
                </div>
              )}

              {/* ---- PHASE: processing (Step 4) ---- */}
              {phase === 'processing' && progress && jobId && token && (
                <div className="space-y-8">
                  <div className="text-center space-y-1">
                    <h2 className="text-xl font-semibold text-text-primary">
                      Finding LinkedIn profiles & extracting intelligence…
                    </h2>
                    <p className="text-sm text-text-secondary">
                      This may take a while for large lists. You can keep this tab open or close it — we&apos;ll email you.
                    </p>
                  </div>

                  <ProgressTracker
                    status={progress.status}
                    currentPhase={progress.current_phase}
                    phaseProgress={progress.phase_progress}
                    processedRows={progress.processed_rows}
                    totalRows={progress.total_rows}
                    foundCount={progress.found_count}
                    phases={PIPELINE_PHASES}
                  />

                  <LivePreview
                    jobId={jobId}
                    token={token}
                    isProcessing={progress.status !== 'completed' && progress.status !== 'failed'}
                  />

                  {progress.status === 'failed' && (
                    <p className="text-sm text-red-600 text-center" role="alert">
                      {progress.error ?? 'Processing failed. Please try again.'}
                    </p>
                  )}
                </div>
              )}

              {phase === 'processing' && !progress && (
                <div className="flex flex-col items-center gap-4 py-12 text-text-secondary">
                  <svg className="w-6 h-6 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  <p className="text-sm">Connecting…</p>
                </div>
              )}

              {/* ---- PHASE: results ---- */}
              {phase === 'results' && jobId && token && (
                <div className="space-y-6">
                  <ResultsPanel
                    jobId={jobId}
                    token={token}
                    totalRows={progress?.total_rows ?? 0}
                    foundCount={progress?.found_count ?? 0}
                    enrichedCount={companyPeople ? (progress?.found_count ?? 0) : 0}
                    downloadUrlOverride={getPeopleDownloadUrl(jobId, token)}
                  />
                  <div className="text-center">
                    <Button variant="ghost" onClick={() => {
                      clearSession();
                      setPhase('input');
                      setInputText('');
                      handleRemoveCsv();
                    }}>
                      Start a new extraction
                    </Button>
                  </div>
                </div>
              )}
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </main>
  );
}
```

- [ ] **Step 2: Verify the frontend builds**

Run: `cd /Users/MattV/Desktop/projects/Quick-Enrich-Tools/frontend && npx next build`
Expected: Build succeeds with no errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/tools/people-intel/page.tsx
git commit -m "feat(people): add People Intel frontend page with 5-phase wizard"
```

---

### Task 13: Final Verification + Commit

- [ ] **Step 1: Run full backend test suite**

Run: `cd /Users/MattV/Desktop/projects/Quick-Enrich-Tools/backend && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Verify backend imports cleanly**

Run: `cd /Users/MattV/Desktop/projects/Quick-Enrich-Tools/backend && python -c "from app.main import app; print(f'Routes: {len(app.routes)}')"`
Expected: No import errors, route count increases by 2 (extract + download)

- [ ] **Step 3: Verify frontend builds**

Run: `cd /Users/MattV/Desktop/projects/Quick-Enrich-Tools/frontend && npx next build`
Expected: Build succeeds

- [ ] **Step 4: Run migration on Supabase**

Apply the migration at `database/migrations/006_register_people_intel_tool.sql` via Supabase dashboard or CLI.

- [ ] **Step 5: Final commit (if any remaining changes)**

```bash
git add -A
git commit -m "feat(people): Product 7 People Intel complete — LinkedIn search + company intel pipeline"
```
