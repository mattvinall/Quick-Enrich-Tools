# Product 5: Google Maps to Company Intel — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Google Maps to Company Intel" tool that discovers businesses via Serper's `/maps` endpoint and feeds them through the existing intel extraction pipeline.

**Architecture:** New Serper Maps service functions → new maps_pipeline.py (Phase 0 discovery + delegate to intel_pipeline) → new maps router → new frontend page. Follows the exact same pattern as Product 4 (G2 Intel) which also has a discovery phase before delegating to the intel pipeline.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy (existing), Serper API `/maps` endpoint (existing API key), Next.js 14, React 18, Tailwind CSS, Framer Motion, Radix UI (all existing)

**Spec:** `docs/superpowers/specs/2026-04-01-product5-maps-intel-design.md`

---

## File Map

### New Files
| File | Responsibility |
|------|---------------|
| `backend/app/routers/maps.py` | API routes: POST `/maps/extract`, GET `/maps/download/{job_id}` |
| `backend/app/workers/maps_pipeline.py` | Phase 0 (Maps discovery via Serper) + delegate to intel_pipeline |
| `frontend/src/app/tools/maps-intel/page.tsx` | Main page (4-step wizard) |
| `frontend/src/components/MapsSearchInput.tsx` | Search terms + location input component |

### Modified Files
| File | Change |
|------|--------|
| `backend/app/services/serper.py` | Add `search_maps()` and `batch_search_maps()` |
| `backend/app/main.py:19-21,31,79` | Import + register maps router, add pipeline to ARQ worker |
| `backend/app/workers/intel_pipeline.py:436` | Add `maps-intel` to download URL prefix logic |
| `frontend/src/lib/api.ts` | Add `submitMapsExtraction()` and `getMapsDownloadUrl()` |
| `frontend/src/lib/tool-registry.ts:14-51` | Add maps-intel tool config |
| `frontend/src/app/page.tsx:5,8-27` | Add maps-intel icon to TOOL_ICONS |

---

## Task 1: Add Serper Maps Service Functions

**Files:**
- Modify: `backend/app/services/serper.py` (append after line 153)

- [ ] **Step 1: Add `search_maps()` function**

Append to `backend/app/services/serper.py`:

```python
async def search_maps(
    client: httpx.AsyncClient,
    query: str,
    location: str = "",
    api_key: str | None = None,
) -> dict[str, object]:
    """Search Google Maps via the Serper /maps endpoint.

    Returns a dict with keys: query, places (list of place dicts).
    Results are cached by query + location for 3 days.
    """
    search_query = f"{query} in {location}" if location else query
    cache_key = make_cache_key("serper_maps", search_query.lower())
    cached = await cache_get(cache_key)
    if cached is not None:
        logger.info("SERPER MAPS CACHE HIT: %s", search_query)
        return cached

    logger.info("SERPER MAPS SEARCH: %s", search_query)

    response = await client.post(
        "https://google.serper.dev/maps",
        headers={
            "X-API-KEY": api_key or settings.serper_api_key,
            "Content-Type": "application/json",
        },
        json={"q": search_query, "gl": "us", "hl": "en"},
        timeout=15.0,
    )
    response.raise_for_status()
    data = response.json()

    places: list[dict[str, object]] = data.get("places", [])
    payload: dict[str, object] = {"query": search_query, "places": places}
    await cache_set(cache_key, payload, 3)  # 3-day cache
    return payload
```

- [ ] **Step 2: Add `batch_search_maps()` function**

Append to `backend/app/services/serper.py`:

```python
async def batch_search_maps(
    searches: list[dict[str, str]],
    max_per_search: int = 20,
    concurrency: int | None = None,
    api_key: str | None = None,
) -> list[dict[str, object]]:
    """Search Google Maps for multiple query+location pairs.

    Each search: {"search_term": str, "location": str}
    Returns a flat list of place dicts, each augmented with
    'search_term' and 'location' keys. Deduplicates by normalized domain.

    max_per_search is capped at 20 per query (single Serper page).
    """
    limit = concurrency if concurrency is not None else settings.serper_concurrency
    semaphore = asyncio.Semaphore(limit)

    async with httpx.AsyncClient() as client:

        async def _search_one(
            search: dict[str, str],
        ) -> tuple[str, str, list[dict[str, object]]]:
            term = search["search_term"]
            loc = search["location"]
            async with semaphore:
                try:
                    result = await retry_async(
                        lambda t=term, l=loc: search_maps(client, t, l, api_key=api_key),
                        max_retries=3,
                        base_delay=1.0,
                    )
                    return term, loc, result.get("places", [])
                except Exception as exc:
                    logger.warning("Maps search failed for '%s in %s': %s", term, loc, exc)
                    return term, loc, []

        raw_outcomes = await asyncio.gather(
            *[_search_one(s) for s in searches],
            return_exceptions=True,
        )

    all_places: list[dict[str, object]] = []
    seen_domains: set[str] = set()
    seen_names: set[str] = set()

    for outcome in raw_outcomes:
        if isinstance(outcome, BaseException):
            continue
        term, loc, places = outcome
        for place in places:
            website = str(place.get("website") or "")
            domain = _parse_domain(website) if website else ""

            # Dedup by domain, or by name+location if no website
            if domain:
                if domain in seen_domains:
                    continue
                seen_domains.add(domain)
            else:
                name_key = f"{str(place.get('title', '')).lower()}|{loc.lower()}"
                if name_key in seen_names:
                    continue
                seen_names.add(name_key)

            place["search_term"] = term
            place["location"] = loc
            all_places.append(place)

            if len(all_places) >= settings.max_rows:
                return all_places

    return all_places
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/serper.py
git commit -m "feat(maps): add search_maps and batch_search_maps to Serper service"
```

---

## Task 2: Create Maps Pipeline Worker

**Files:**
- Create: `backend/app/workers/maps_pipeline.py`
- Modify: `backend/app/workers/intel_pipeline.py:436`
- Modify: `backend/app/main.py:19-21,31`

- [ ] **Step 1: Create `maps_pipeline.py`**

Create `backend/app/workers/maps_pipeline.py` following the exact pattern of `g2_pipeline.py`:

```python
"""Google Maps to Company Intel pipeline.

Phase 0: Search Google Maps via Serper to discover businesses.
Phases 1-5: Delegates to existing intel pipeline (Resolve -> Crawl -> Extract -> Enrich -> Deliver).
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Job, JobResult
from app.services.serper import batch_search_maps
from app.workers.intel_pipeline import run_intel_pipeline, update_job_progress

logger = logging.getLogger(__name__)

_INSERT_BATCH_SIZE = 1000


async def run_maps_pipeline(ctx: dict, job_id: str) -> None:
    """Main entry point for the Maps Intel pipeline.

    Phase 0: Search Google Maps to discover businesses, create JobResult rows.
    Phases 1-5: Delegate to existing intel pipeline.
    """
    parsed_job_id = uuid.UUID(job_id)

    async with AsyncSessionLocal() as db:
        job_result = await db.execute(select(Job).where(Job.id == parsed_job_id))
        job = job_result.scalar_one()
        config = job.config or {}

        job.status = "maps_searching"
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

    # ── Phase 0: Maps Discovery ─────────────────────────────────────
    searches: list[dict[str, str]] = config.get("searches", [])
    max_per_search: int = config.get("max_per_search", 20)

    logger.info(
        "Maps pipeline starting for job_id=%s: %d searches, max_per_search=%d",
        job_id, len(searches), max_per_search,
    )

    try:
        places = await batch_search_maps(
            searches, max_per_search=max_per_search,
        )
    except Exception as exc:
        logger.exception("Maps search failed for job_id=%s: %s", job_id, exc)
        async with AsyncSessionLocal() as db:
            job_result = await db.execute(select(Job).where(Job.id == parsed_job_id))
            job = job_result.scalar_one()
            job.status = "failed"
            job.error_message = f"Maps search failed: {exc}"
            await db.commit()
        raise

    if not places:
        async with AsyncSessionLocal() as db:
            job_result = await db.execute(select(Job).where(Job.id == parsed_job_id))
            job = job_result.scalar_one()
            job.status = "failed"
            job.error_message = "No businesses found for the given search terms and location."
            await db.commit()
        return

    # ── Create JobResult rows in sub-batches ─────────────────────────
    from urllib.parse import urlparse

    def _extract_domain(url: str) -> str:
        url = url.strip().lower()
        for prefix in ("https://", "http://"):
            if url.startswith(prefix):
                url = url[len(prefix):]
                break
        if url.startswith("www."):
            url = url[4:]
        for sep in ("/", "?", "#"):
            idx = url.find(sep)
            if idx != -1:
                url = url[:idx]
        return url

    async with AsyncSessionLocal() as db:
        for batch_start in range(0, len(places), _INSERT_BATCH_SIZE):
            batch = places[batch_start:batch_start + _INSERT_BATCH_SIZE]
            job_results = []
            for i, p in enumerate(batch):
                website = str(p.get("website") or "")
                domain = _extract_domain(website) if website else ""
                cid = str(p.get("cid") or "")
                maps_url = f"https://www.google.com/maps/place/?cid={cid}" if cid else ""

                job_results.append(
                    JobResult(
                        job_id=parsed_job_id,
                        row_index=batch_start + i,
                        input_data={
                            "input": website or str(p.get("title", "")),
                            "input_type": "url" if website else "name",
                            "search_term": str(p.get("search_term", "")),
                            "location": str(p.get("location", "")),
                            "business_name": str(p.get("title", "")),
                            "category": str(p.get("category", "")),
                            "maps_address": str(p.get("address", "")),
                            "maps_phone": str(p.get("phoneNumber", "")),
                            "rating": p.get("rating"),
                            "review_count": p.get("ratingCount"),
                            "latitude": p.get("latitude"),
                            "longitude": p.get("longitude"),
                            "google_cid": cid,
                            "google_maps_url": maps_url,
                        },
                        raw_domain=domain or None,
                        status="pending",
                    )
                )
            db.add_all(job_results)
            await db.flush()

        # Update job with actual count
        job_result = await db.execute(select(Job).where(Job.id == parsed_job_id))
        job = job_result.scalar_one()
        job.total_rows = len(places)
        await db.commit()

    logger.info(
        "Maps Phase 0 complete for job_id=%s: %d businesses discovered",
        job_id, len(places),
    )

    try:
        async with AsyncSessionLocal() as progress_db:
            await update_job_progress(
                progress_db, parsed_job_id, "maps_search",
                len(searches), len(searches),
                processed_rows=0,
            )
    except Exception:
        pass

    # ── Phases 1-5: Delegate to existing intel pipeline ──────────────
    await run_intel_pipeline({}, job_id)
```

- [ ] **Step 2: Update download URL prefix in `intel_pipeline.py`**

In `backend/app/workers/intel_pipeline.py`, change line 436 from:

```python
        dl_prefix = "g2" if job.tool_slug == "g2-intel" else "intel"
```

to:

```python
        dl_slug_map = {"g2-intel": "g2", "maps-intel": "maps"}
        dl_prefix = dl_slug_map.get(job.tool_slug, "intel")
```

- [ ] **Step 3: Register maps pipeline in `main.py`**

In `backend/app/main.py`, add import at line 21 (after `from app.routers import g2`):

```python
from app.routers import maps
```

Add to the `all_functions` list in `_run_arq_worker()` at line 31:

```python
    from app.workers.maps_pipeline import run_maps_pipeline
```

Update line 31:

```python
    all_functions = list(P2WorkerSettings.functions) + [run_intel_pipeline, run_g2_pipeline, run_maps_pipeline]
```

Add router at line 79 (after `app.include_router(g2.router, prefix="/api/v1")`):

```python
app.include_router(maps.router, prefix="/api/v1")
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/workers/maps_pipeline.py backend/app/workers/intel_pipeline.py backend/app/main.py
git commit -m "feat(maps): add maps pipeline worker and register in main app"
```

---

## Task 3: Create Maps API Router

**Files:**
- Create: `backend/app/routers/maps.py`

- [ ] **Step 1: Create the router file**

Create `backend/app/routers/maps.py` following the exact pattern of `g2.py`:

```python
"""API endpoints for the Google Maps to Company Intel tool."""

import csv
import io
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_token, verify_token
from app.config import settings
from app.database import get_db
from app.models import Job, JobResult

router = APIRouter(prefix="/maps", tags=["maps"])


# ── Request / Response Models ────────────────────────────────────────

class ExtractionOptions(BaseModel):
    industry_description: bool = True
    target_market: bool = True
    company_people: bool = True
    homepage_raw_text: bool = False


class MapsSearchItem(BaseModel):
    search_term: str
    location: str


class MapsExtractRequest(BaseModel):
    # Interactive mode
    search_terms: list[str] = []
    location: str = ""
    # CSV mode (overrides search_terms + location if present)
    searches: list[MapsSearchItem] = []
    # Shared config
    max_per_search: int = 20
    options: ExtractionOptions = ExtractionOptions()
    quickenrich_api_key: str = ""
    job_titles: list[str] = []
    max_contacts: int = 3


# ── Endpoints ────────────────────────────────────────────────────────

@router.post("/extract")
async def submit_maps_extraction(
    body: MapsExtractRequest,
    token_payload: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Validate inputs, create Job, and launch maps_pipeline."""
    # Normalize: convert interactive mode into searches list
    if body.searches:
        searches = [s.model_dump() for s in body.searches]
    elif body.search_terms and body.location:
        searches = [
            {"search_term": t.strip(), "location": body.location.strip()}
            for t in body.search_terms
            if t.strip()
        ]
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide either search_terms + location, or a searches list.",
        )

    if not searches:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one search term is required.",
        )

    if len(searches) > 500:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Maximum 500 search term + location combinations.",
        )

    max_per = body.max_per_search
    if max_per < 1 or max_per > 20:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="max_per_search must be between 1 and 20.",
        )

    total_expected = len(searches) * max_per
    if total_expected > 50_000:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Expected {total_expected} results exceeds the 50,000 limit. Reduce search terms or max per search.",
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
        "searches": searches,
        "max_per_search": max_per,
        "options": opts.model_dump(),
        "quickenrich_api_key": body.quickenrich_api_key,
        "job_titles": body.job_titles,
        "max_contacts": body.max_contacts,
    }

    job = Job(
        email_capture_id=uuid.UUID(email_capture_id),
        tool_slug="maps-intel",
        status="pending",
        total_rows=0,  # Updated after Maps discovery
        config=job_config,
    )
    db.add(job)
    await db.flush()

    # Run pipeline as background task
    import asyncio
    from app.workers.maps_pipeline import run_maps_pipeline
    asyncio.create_task(run_maps_pipeline({}, str(job.id)))

    new_token = create_token(email, str(job.id))
    return {
        "job_id": str(job.id),
        "total_searches": len(searches),
        "token": new_token,
    }


# ── CSV Download ─────────────────────────────────────────────────────

_BATCH_SIZE = 500
_MAPS_COLUMNS = [
    "search_term", "location", "business_name", "category",
    "maps_address", "maps_phone", "website", "rating", "review_count",
    "latitude", "longitude", "google_maps_url", "status",
]
_CONTACT_FIELDS = ["Title", "First Name", "Last Name", "Email", "Phone", "LinkedIn"]


def _extract_maps_row(result: JobResult, options: dict, max_contacts: int = 5) -> list[str]:
    input_data = result.input_data or {}
    extracted = result.extracted_data or {}

    maps_base = [
        str(input_data.get("search_term", "")),
        str(input_data.get("location", "")),
        str(input_data.get("business_name", "")),
        str(input_data.get("category", "")),
        str(input_data.get("maps_address", "")),
        str(input_data.get("maps_phone", "")),
        result.normalized_domain or result.raw_domain or "",
        str(input_data.get("rating") or ""),
        str(input_data.get("review_count") or ""),
        str(input_data.get("latitude") or ""),
        str(input_data.get("longitude") or ""),
        str(input_data.get("google_maps_url", "")),
        result.status,
    ]

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

    return maps_base + intel_cells + contact_cells


def _build_maps_headers(options: dict, max_contacts: int = 5) -> list[str]:
    headers = list(_MAPS_COLUMNS)

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


async def _stream_maps_csv(job: Job, db: AsyncSession) -> AsyncGenerator[bytes, None]:
    yield b"\xef\xbb\xbf"

    config = job.config or {}
    options = config.get("options", {})

    headers = _build_maps_headers(options)

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
            writer.writerow(_extract_maps_row(result, options))
        yield buf.getvalue().encode("utf-8")

        if len(rows) < _BATCH_SIZE:
            break
        offset += _BATCH_SIZE


@router.get("/download/{job_id}")
async def download_maps_results(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
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
    filename = f"maps_intel_results_{timestamp}.csv"

    return StreamingResponse(
        _stream_maps_csv(job, db),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/routers/maps.py
git commit -m "feat(maps): add maps router with extract and download endpoints"
```

---

## Task 4: Add Frontend API Client Functions

**Files:**
- Modify: `frontend/src/lib/api.ts` (append after line 208)

- [ ] **Step 1: Add Maps types and functions to `api.ts`**

Append to `frontend/src/lib/api.ts`:

```typescript
// ── Maps Intel ─────────────────────────────────────────────────────

export interface MapsSearchItem {
  search_term: string;
  location: string;
}

export interface MapsExtractRequest {
  // Interactive mode (same location for all terms)
  search_terms?: string[];
  location?: string;
  // CSV mode (per-row locations) — overrides search_terms + location if present
  searches?: MapsSearchItem[];
  // Shared config
  max_per_search: number;
  options: ExtractionOptions;
  quickenrich_api_key: string;
  job_titles: string[];
  max_contacts: number;
}

export interface MapsExtractResponse {
  job_id: string;
  total_searches: number;
  token: string;
}

export function submitMapsExtraction(
  body: MapsExtractRequest,
  token: string,
): Promise<MapsExtractResponse> {
  return fetchAPI<MapsExtractResponse>(`${API_URL}/api/v1/maps/extract`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  });
}

export function getMapsDownloadUrl(jobId: string, token: string): string {
  return `${API_URL}/api/v1/maps/download/${jobId}?token=${encodeURIComponent(token)}`;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat(maps): add maps extraction API client functions"
```

---

## Task 5: Register Tool and Add Home Page Icon

**Files:**
- Modify: `frontend/src/lib/tool-registry.ts:14-51`
- Modify: `frontend/src/app/page.tsx:5,8-27`

- [ ] **Step 1: Add maps-intel to tool registry**

In `frontend/src/lib/tool-registry.ts`, add a new entry to the `tools` array after the g2-intel entry (before the closing `];`):

```typescript
  {
    slug: "maps-intel",
    name: "Google Maps to Company Intel",
    description:
      "Search Google Maps by category and location to discover businesses, then extract business intelligence, contacts, and more.",
    isActive: true,
    backendUrl: API_BASE_URL,
    requiredColumns: [],
    optionalColumns: [],
    columnPatterns: {},
  },
```

- [ ] **Step 2: Add icon to home page**

In `frontend/src/app/page.tsx`:

Update the import on line 5 to add `Map`:
```typescript
import { ArrowRight, Grid3X3, Map, MapPin, Search, Users } from "lucide-react";
```

Add to `TOOL_ICONS` object after the "g2-intel" entry:
```typescript
  "maps-intel": (
    <div className="flex items-center gap-1 text-primary">
      <Map className="w-5 h-5" />
      <Users className="w-4 h-4" />
    </div>
  ),
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/tool-registry.ts frontend/src/app/page.tsx
git commit -m "feat(maps): register maps-intel tool and add home page icon"
```

---

## Task 6: Create MapsSearchInput Component

**Files:**
- Create: `frontend/src/components/MapsSearchInput.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/src/components/MapsSearchInput.tsx`:

```tsx
'use client';

import { useState, useRef } from 'react';
import { MapPin, Search, Upload, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';
import Papa from 'papaparse';

interface MapsSearchItem {
  search_term: string;
  location: string;
}

interface MapsSearchInputProps {
  searchTerms: string[];
  onSearchTermsChange: (terms: string[]) => void;
  location: string;
  onLocationChange: (loc: string) => void;
  maxPerSearch: number;
  onMaxPerSearchChange: (n: number) => void;
  /** Set when CSV has per-row locations (overrides interactive mode) */
  csvSearches: MapsSearchItem[];
  onCsvSearchesChange: (searches: MapsSearchItem[]) => void;
}

// Capped at 20 until Serper /maps pagination is verified at runtime.
// Each Serper /maps query returns ~20 results per page.
const MAX_OPTIONS = [20];

export default function MapsSearchInput({
  searchTerms,
  onSearchTermsChange,
  location,
  onLocationChange,
  maxPerSearch,
  onMaxPerSearchChange,
  csvSearches,
  onCsvSearchesChange,
}: MapsSearchInputProps) {
  const [mode, setMode] = useState<'interactive' | 'csv'>('interactive');
  const [rawText, setRawText] = useState(searchTerms.join('\n'));
  const [csvError, setCsvError] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);

  function handleTextChange(value: string) {
    setRawText(value);
    const terms = value
      .split('\n')
      .map((l) => l.trim())
      .filter(Boolean);
    onSearchTermsChange(terms);
  }

  function handleCSVUpload(file: File) {
    setCsvError('');
    Papa.parse(file, {
      header: true,
      skipEmptyLines: true,
      complete(results) {
        const headers = results.meta.fields || [];
        const termCol = headers.find((h) => /search.?term|query|keyword|category/i.test(h));
        const locCol = headers.find((h) => /location|city|state|area|region/i.test(h));

        if (!termCol) {
          setCsvError('CSV must have a column matching "search_term", "query", "keyword", or "category".');
          return;
        }

        const terms: string[] = [];
        const locations = new Set<string>();
        const perRowSearches: MapsSearchItem[] = [];

        for (const row of results.data as Record<string, string>[]) {
          const term = (row[termCol] || '').trim();
          if (!term) continue;
          terms.push(term);
          const loc = locCol ? (row[locCol] || '').trim() : '';
          if (loc) locations.add(loc);
          if (locCol && loc) {
            perRowSearches.push({ search_term: term, location: loc });
          }
        }

        onSearchTermsChange(terms);
        setRawText(terms.join('\n'));

        if (locations.size === 1) {
          // All rows share same location — use interactive mode
          onLocationChange([...locations][0]);
          onCsvSearchesChange([]);
        } else if (locations.size > 1 && perRowSearches.length > 0) {
          // Different locations per row — use CSV mode (per-row searches)
          onCsvSearchesChange(perRowSearches);
        }
      },
      error() {
        setCsvError('Failed to parse CSV file.');
      },
    });
  }

  const estimatedTotal = searchTerms.length * maxPerSearch;

  return (
    <div className="space-y-5">
      {/* Mode toggle */}
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => setMode('interactive')}
          className={cn(
            'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors',
            mode === 'interactive'
              ? 'bg-primary text-white'
              : 'bg-gray-100 text-text-secondary hover:bg-gray-200',
          )}
        >
          <Search className="w-3.5 h-3.5" />
          Type searches
        </button>
        <button
          type="button"
          onClick={() => setMode('csv')}
          className={cn(
            'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors',
            mode === 'csv'
              ? 'bg-primary text-white'
              : 'bg-gray-100 text-text-secondary hover:bg-gray-200',
          )}
        >
          <Upload className="w-3.5 h-3.5" />
          Upload CSV
        </button>
      </div>

      {/* Search terms */}
      {mode === 'interactive' ? (
        <div className="space-y-2">
          <Label htmlFor="search-terms">Search terms (one per line)</Label>
          <Textarea
            id="search-terms"
            rows={5}
            placeholder={"plumber\nelectrician\nHVAC repair\nroofer"}
            value={rawText}
            onChange={(e) => handleTextChange(e.target.value)}
            className="font-mono text-sm"
          />
          {searchTerms.length > 0 && (
            <p className="text-xs text-text-secondary">
              {searchTerms.length} search {searchTerms.length === 1 ? 'term' : 'terms'}
            </p>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          <Label>Upload CSV with search terms</Label>
          <div
            className="border-2 border-dashed border-border rounded-lg p-6 text-center cursor-pointer hover:border-primary/40 transition-colors"
            onClick={() => fileRef.current?.click()}
          >
            <Upload className="w-6 h-6 mx-auto mb-2 text-text-secondary" />
            <p className="text-sm text-text-secondary">
              Click to upload CSV with <span className="font-medium">search_term</span> column
            </p>
            <p className="text-xs text-text-secondary mt-1">
              Optional: include a <span className="font-medium">location</span> column
            </p>
          </div>
          <input
            ref={fileRef}
            type="file"
            accept=".csv"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) handleCSVUpload(file);
            }}
          />
          {csvError && <p className="text-sm text-red-600">{csvError}</p>}
          {searchTerms.length > 0 && mode === 'csv' && (
            <div className="flex items-center gap-2 text-sm text-text-secondary bg-gray-50 rounded-md px-3 py-2">
              <span className="font-medium text-text-primary">{searchTerms.length}</span> search terms loaded from CSV
              <button
                type="button"
                onClick={() => {
                  onSearchTermsChange([]);
                  setRawText('');
                  if (fileRef.current) fileRef.current.value = '';
                }}
                className="ml-auto text-text-secondary hover:text-red-500"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          )}
        </div>
      )}

      {/* Location */}
      <div className="space-y-2">
        <Label htmlFor="location">
          <span className="flex items-center gap-1.5">
            <MapPin className="w-3.5 h-3.5" />
            Location
          </span>
        </Label>
        <Input
          id="location"
          placeholder="Miami, FL"
          value={location}
          onChange={(e) => onLocationChange(e.target.value)}
        />
        <p className="text-xs text-text-secondary">
          City, state, or region to search in
        </p>
      </div>

      {/* Max per search */}
      <div className="space-y-2">
        <Label htmlFor="max-per-search">Max results per search term</Label>
        <select
          id="max-per-search"
          value={maxPerSearch}
          onChange={(e) => onMaxPerSearchChange(Number(e.target.value))}
          className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        >
          {MAX_OPTIONS.map((n) => (
            <option key={n} value={n}>
              {n} businesses
            </option>
          ))}
        </select>
      </div>

      {/* Estimated total */}
      {searchTerms.length > 0 && location && (
        <div className="bg-primary/5 border border-primary/20 rounded-lg px-4 py-3">
          <p className="text-sm text-text-primary">
            <span className="font-semibold">{searchTerms.length}</span>{' '}
            {searchTerms.length === 1 ? 'search' : 'searches'} in{' '}
            <span className="font-semibold">{location}</span>
            {' = '}
            <span className="font-semibold text-primary">~{estimatedTotal.toLocaleString()}</span>{' '}
            estimated businesses
          </p>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/MapsSearchInput.tsx
git commit -m "feat(maps): create MapsSearchInput component with interactive and CSV modes"
```

---

## Task 7: Create Maps Intel Page

**Files:**
- Create: `frontend/src/app/tools/maps-intel/page.tsx`

- [ ] **Step 1: Create the page**

Create `frontend/src/app/tools/maps-intel/page.tsx` following the exact G2 Intel page pattern:

```tsx
'use client';

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

import MapsSearchInput from '@/components/MapsSearchInput';
import ExtractionSettings from '@/components/ExtractionSettings';
import EmailGate from '@/components/EmailGate';
import ProgressTracker from '@/components/ProgressTracker';
import LivePreview from '@/components/LivePreview';
import ResultsPanel from '@/components/ResultsPanel';
import { useSSE } from '@/hooks/useSSE';
import { captureEmail, submitMapsExtraction, getMapsDownloadUrl } from '@/lib/api';

type Phase = 'search' | 'configure' | 'submit' | 'processing' | 'results';

const PHASE_ORDER: Phase[] = ['search', 'configure', 'submit', 'processing', 'results'];

const PIPELINE_PHASES = ['Search', 'Resolve', 'Crawl', 'Extract', 'Enrich', 'Deliver'] as const;

const STEP_MAP: Partial<Record<Phase, { step: number; total: number; label: string }>> = {
  search:     { step: 1, total: 4, label: 'Search configuration' },
  configure:  { step: 2, total: 4, label: 'Extraction settings' },
  submit:     { step: 3, total: 4, label: 'Enter your email' },
  processing: { step: 4, total: 4, label: 'Processing' },
};

function phaseIndex(p: Phase): number {
  return PHASE_ORDER.indexOf(p);
}

export default function MapsIntelPage() {
  const [phase, setPhase] = useState<Phase>('search');
  const [direction, setDirection] = useState<'forward' | 'back'>('forward');

  // Search config
  const [searchTerms, setSearchTerms] = useState<string[]>([]);
  const [location, setLocation] = useState('');
  const [maxPerSearch, setMaxPerSearch] = useState(20);
  const [csvSearches, setCsvSearches] = useState<{ search_term: string; location: string }[]>([]);

  // Extraction options
  const [industryDescription, setIndustryDescription] = useState(true);
  const [targetMarket, setTargetMarket] = useState(true);
  const [companyPeople, setCompanyPeople] = useState(true);
  const [homepageRawText, setHomepageRawText] = useState(false);

  // QuickEnrich API key (Serper key not needed — backend uses its own for Maps + resolve)
  const [quickenrichApiKey, setQuickenrichApiKey] = useState('');

  // Contact config
  const [jobTitles, setJobTitles] = useState<string[]>(['CEO', 'Owner']);
  const [maxContacts, setMaxContacts] = useState(3);

  // Job state — restore from localStorage
  const [jobId, setJobId] = useState<string | null>(() => {
    if (typeof window === 'undefined') return null;
    return localStorage.getItem('qe_maps_job_id');
  });
  const [token, setToken] = useState<string | null>(() => {
    if (typeof window === 'undefined') return null;
    return localStorage.getItem('qe_maps_token');
  });

  // Submit state
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');

  // Persist job session
  useEffect(() => {
    if (jobId && token) {
      localStorage.setItem('qe_maps_job_id', jobId);
      localStorage.setItem('qe_maps_token', token);
    }
  }, [jobId, token]);

  // Resume saved job on mount
  useEffect(() => {
    if (jobId && token && phase === 'search') {
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
    localStorage.removeItem('qe_maps_job_id');
    localStorage.removeItem('qe_maps_token');
    setJobId(null);
    setToken(null);
  }

  // Validation
  const hasSearches = searchTerms.length > 0 && location.trim().length > 0;
  const hasOptions = industryDescription || targetMarket || companyPeople || homepageRawText;
  const canSubmit = hasSearches && hasOptions;

  const estimatedTotal = searchTerms.length * maxPerSearch;

  async function handleEmailSubmit(email: string) {
    setIsSubmitting(true);
    setSubmitError('');

    try {
      const capture = await captureEmail(email, 'maps-intel', 'maps-intel-page');

      // Use per-row searches if CSV had different locations, otherwise interactive mode
      const sharedOpts = {
        max_per_search: maxPerSearch,
        options: {
          industry_description: industryDescription,
          target_market: targetMarket,
          company_people: companyPeople,
          homepage_raw_text: homepageRawText,
        },
        quickenrich_api_key: quickenrichApiKey,
        job_titles: companyPeople ? jobTitles : [],
        max_contacts: companyPeople ? maxContacts : 1,
      };

      const body = csvSearches.length > 0
        ? { ...sharedOpts, searches: csvSearches }
        : { ...sharedOpts, search_terms: searchTerms, location: location.trim() };

      const result = await submitMapsExtraction(body, capture.token);

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
            Google Maps to Company Intel
          </h1>
          <p className="text-text-secondary max-w-xl mx-auto">
            Search Google Maps by category and location to discover businesses and extract business intelligence
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
              {/* ---- PHASE: search (Step 1) ---- */}
              {phase === 'search' && (
                <div className="space-y-6">
                  <div>
                    <h2 className="text-lg font-semibold text-text-primary">Search Google Maps</h2>
                    <p className="text-sm text-text-secondary mt-0.5">
                      Enter search terms and a location to discover businesses.
                    </p>
                  </div>

                  <MapsSearchInput
                    searchTerms={searchTerms}
                    onSearchTermsChange={setSearchTerms}
                    location={location}
                    onLocationChange={setLocation}
                    maxPerSearch={maxPerSearch}
                    onMaxPerSearchChange={setMaxPerSearch}
                    csvSearches={csvSearches}
                    onCsvSearchesChange={setCsvSearches}
                  />

                  <div className="flex justify-end">
                    <Button onClick={() => navigate('configure')} disabled={!hasSearches} className="gap-2">
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
                      Choose what data to extract from discovered businesses.
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
                    hasCompanyNames={false}
                    quickenrichApiKey={quickenrichApiKey}
                    onQuickenrichApiKeyChange={setQuickenrichApiKey}
                    serperApiKey=""
                    onSerperApiKeyChange={() => {}}
                    jobTitles={jobTitles}
                    onJobTitlesChange={setJobTitles}
                    maxContacts={maxContacts}
                    onMaxContactsChange={setMaxContacts}
                  />

                  <div className="flex gap-3 pt-2">
                    <Button variant="outline" onClick={() => navigate('search')}>Back</Button>
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
                      Enter your email to start searching{' '}
                      <span className="font-medium text-text-primary">
                        {searchTerms.length} {searchTerms.length === 1 ? 'term' : 'terms'}
                      </span>{' '}
                      in{' '}
                      <span className="font-medium text-text-primary">{location}</span>{' '}
                      for up to{' '}
                      <span className="font-medium text-text-primary">
                        {estimatedTotal.toLocaleString()} businesses
                      </span>.
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
                      Searching Google Maps & extracting intelligence...
                    </h2>
                    <p className="text-sm text-text-secondary">
                      This may take a while for large searches. You can keep this tab open or close it — we&apos;ll email you.
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
                  <p className="text-sm">Connecting...</p>
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
                    downloadUrlOverride={getMapsDownloadUrl(jobId, token)}
                  />
                  <div className="text-center">
                    <Button variant="ghost" onClick={() => {
                      clearSession();
                      setPhase('search');
                      setSearchTerms([]);
                      setLocation('');
                    }}>
                      Start a new search
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

- [ ] **Step 2: Commit**

```bash
git add frontend/src/app/tools/maps-intel/page.tsx
git commit -m "feat(maps): create maps-intel page with 4-step wizard"
```

---

## Task 8: Smoke Test & Verify

- [ ] **Step 1: Verify backend starts without import errors**

```bash
cd backend && python -c "from app.main import app; print('Backend imports OK')"
```

Expected: `Backend imports OK`

- [ ] **Step 2: Verify frontend builds without TypeScript errors**

```bash
cd frontend && npx tsc --noEmit
```

Expected: No errors

- [ ] **Step 3: Final commit with all files**

If any fixups were needed, commit them:
```bash
git add -A
git commit -m "fix(maps): resolve import and type errors from smoke test"
```
