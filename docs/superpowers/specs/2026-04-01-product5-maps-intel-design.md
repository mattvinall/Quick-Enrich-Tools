# Product 5: Google Maps to Company Intel — Design Spec

**Date:** 2026-04-01
**Status:** Draft
**Tool Slug:** `maps-intel`

## 1. Purpose

Allow users to search Google Maps by business category and location (e.g., "plumber in Miami, FL"), discover businesses, and then extract structured business intelligence from those businesses using the existing intel pipeline. This is essentially "Google Maps discovery" feeding into the Product 3 enrichment engine.

**Users:** Researchers, sales teams, marketers, or analysts needing quick company intelligence from local business searches.

## 2. Data Source: Serper `/maps` Endpoint

**Why Serper over Apify or Google Places API:**
- QuickEnrich already uses Serper (`backend/app/services/serper.py`) — zero new dependencies
- Same API key (`SERPER_API_KEY`), same `httpx` client, same retry/cache infrastructure
- Cost: ~$0.50-1.00 per 1,000 queries (vs Apify at $4/1K or Google Places at $25-32/1K)
- Speed: sub-second responses, up to 300 QPS
- Returns: business name, website, phone, address, rating, review count, category, coordinates, CID

**Serper `/maps` endpoint:**
```
POST https://google.serper.dev/maps
Headers: X-API-KEY: <key>, Content-Type: application/json
Body: { "q": "plumber in Miami FL", "gl": "us", "hl": "en" }
```

**Response fields per place:**
- `title` (business name)
- `address` (full address)
- `latitude`, `longitude`
- `category` (primary business category)
- `phoneNumber`
- `website` (business website URL)
- `rating` (1-5 scale)
- `ratingCount` (total reviews)
- `cid` (Google unique place identifier)
- `thumbnailUrl` (listing thumbnail)

**Limitations:**
- ~20 results per query (Google Maps natural limit)
- No email addresses (handled by crawl+extract pipeline)
- No social media links (handled by crawl+extract pipeline)
- Pagination support via `page` parameter needs runtime verification — if unsupported, max_per_search caps at 20

## 3. User Flow (4-Step Wizard)

Follows the same phase state machine pattern as Products 3 and 4.

### Step 1: Search Configuration (`search` phase)

**Two input modes:**

**A) Interactive Search (default):**
- Search terms textarea (one per line): e.g., "plumber", "electrician", "HVAC repair"
- Location text field: e.g., "Miami, FL" or "New York, NY"
- Max results per search term: dropdown (20, 40, 60, 80, 100) — default 20
  - Values over 20 require multiple paginated Serper calls (20 results per page)
- Estimated total preview: `{N terms} x {max per search} = ~{total} businesses`

Interactive mode expands to N pairs: each search_term paired with the shared location.

**B) CSV Upload:**
- Upload CSV with columns: `search_term` and `location`
- Allows batching different search terms across different locations
- Auto-detect column mapping (same pattern as Product 2)
- Max results per row: same dropdown

**Validation:**
- At least one search term required
- Location required (cannot search without geographic context)
- Max 500 unique search term + location combinations
- Max 50,000 total expected results (terms x max_per_search)

### Step 2: Extraction Settings (`configure` phase)

Reuses the existing `ExtractionSettings` component:
- Industry & Description (default: checked)
- Target Market (default: checked)
- Company's People (default: checked)
  - QuickEnrich API key input
  - Job titles selector
  - Max contacts per company (1-5)
- Homepage Raw Text (default: unchecked)

`hasCompanyNames` is set to `false` — the backend uses its own Serper API key for the website resolution fallback (for the ~10-20% of Maps listings without websites). This is a pipeline-internal operation, not user-initiated name-to-domain resolution.

### Step 3: Email Gate (`submit` phase)

Reuses `EmailGate` component. Flow: `captureEmail()` returns a JWT token, then `submitMapsExtraction()` uses that token (same pattern as G2). Summary text:
> "Search {N} terms in {location} for up to {total} businesses."

### Step 4: Processing (`processing` phase)

6-phase pipeline with `ProgressTracker` (deduplication folded into Search phase since it takes milliseconds):
1. **Search** — Querying Google Maps via Serper + deduplicating results
2. **Resolve** — Resolving websites for entries without one
3. **Crawl** — Scraping business websites
4. **Extract** — AI-powered data extraction
5. **Enrich** — Contact enrichment via QuickEnrich
6. **Deliver** — Preparing CSV and sending email

Progress tracked via `useSSE` hook polling `/api/v1/jobs/{job_id}/sse` (same as Products 3 & 4).

Error handling follows the existing pattern — failed jobs display `error_message` via ProgressTracker.

### Results Phase

Reuses `ResultsPanel` with Maps-specific columns in the preview table.

## 4. Backend Architecture

### 4.1 New Files

| File | Purpose |
|------|---------|
| `backend/app/routers/maps.py` | API routes: POST `/maps/extract`, GET `/maps/download/{job_id}` |
| `backend/app/workers/maps_pipeline.py` | Pipeline orchestration with Maps discovery + intel delegation |

### 4.2 Modified Files

| File | Change |
|------|--------|
| `backend/app/services/serper.py` | Add `search_maps()` and `batch_search_maps()` |
| `backend/app/main.py` | Register maps router |
| `frontend/src/lib/tool-registry.ts` | Add maps-intel tool config |
| `frontend/src/lib/api.ts` | Add `submitMapsExtraction()` and `getMapsDownloadUrl()` |

### 4.3 API Endpoints

**`POST /api/v1/maps/extract`**

Single unified request model. The backend accepts either format — if `searches` is present, `search_terms` and `location` are ignored:

```python
class MapsExtractRequest(BaseModel):
    # Interactive mode (simple: same location for all terms)
    search_terms: list[str] = []
    location: str = ""

    # CSV mode (advanced: different location per term)
    searches: list[MapsSearchItem] = []  # overrides search_terms + location if present

    # Shared config
    max_per_search: int = 20
    options: ExtractionOptions = ExtractionOptions()
    quickenrich_api_key: str = ""
    job_titles: list[str] = []
    max_contacts: int = 3

class MapsSearchItem(BaseModel):
    search_term: str
    location: str
```

Validation: if `searches` is empty, `search_terms` and `location` are required. The backend normalizes interactive mode into the same `searches` list internally: `[{search_term: t, location: location} for t in search_terms]`.

Response:
```json
{
  "job_id": "uuid",
  "total_searches": 2,
  "token": "jwt_token"
}
```

**`GET /api/v1/maps/download/{job_id}?token=...`**
- Streams CSV with BOM for Excel compatibility
- Filename: `maps_intel_results_{YYYYMMDD_HHMMSS}.csv`

### 4.4 Pipeline Design

**Phase 0: Maps Discovery (Search phase)**

```
For each (search_term, location) pair:
  1. Build query: "{search_term} in {location}"
  2. Call Serper /maps endpoint
  3. If max_per_search > 20: paginate (page=1,2,...) until max reached
  4. For each result:
     - Create JobResult with:
       - input_data: {
           search_term, location, business_name, category, address,
           phone, rating, review_count, latitude, longitude,
           google_cid, google_maps_url, website (if present)
         }
       - raw_domain: extracted from website field (if present)
       - status: "discovered"
  5. Deduplicate by normalized website domain (keep first occurrence)
     - For entries without website: deduplicate by business_name + search location
       (use the location from the search query, not parsed from the address)
  6. Update job.total_rows with actual discovered count
```

Google Maps URL construction: `https://www.google.com/maps/place/?cid={cid}` (using the CID from Serper response).

**Phases 1-5: Intel Pipeline Delegation**

Same pattern as Product 4 (G2):
- Results with `raw_domain` set skip the resolve phase
- Results without `raw_domain` go through Serper web search resolution using the backend's Serper API key (query: `"{business_name}" {location} official website`)
- Then: Crawl -> Extract -> Enrich -> Deliver

### 4.5 Serper Service Additions

New functions in `backend/app/services/serper.py`:

```python
async def search_maps(
    client: httpx.AsyncClient,
    query: str,
    location: str = "",
    page: int = 1,
    api_key: str | None = None,
) -> dict:
    """Search Google Maps via Serper /maps endpoint."""
    search_query = f"{query} in {location}" if location else query
    cache_key = make_cache_key("serper_maps", search_query.lower(), str(page))
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

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
    places = data.get("places", [])
    payload = {"query": search_query, "places": places, "page": page}
    await cache_set(cache_key, payload, 3)  # 3-day cache (same as G2)
    return payload


async def batch_search_maps(
    searches: list[dict],
    max_per_search: int = 20,
    concurrency: int | None = None,
    api_key: str | None = None,
) -> list[dict]:
    """Search multiple queries, paginating as needed, dedup by domain.

    Each search: {"search_term": str, "location": str}
    Returns flat list of unique place results.
    Uses settings.serper_concurrency (50) as default concurrency.
    """
    ...
```

### 4.6 Database Usage

No schema changes. Uses existing tables:

**`jobs` table:**
- `tool_slug`: `"maps-intel"`
- `config`: `{"searches": [...], "max_per_search": 20, "options": {...}, "quickenrich_api_key": "...", "job_titles": [...], "max_contacts": 3}`
- `status`: follows existing pattern — `pending` -> `maps_searching` -> `resolving` -> `delivering` -> `completed` (intermediate phases tracked via `current_phase` and `phase_progress` JSONB fields, not as top-level status values)

**`job_results` table:**
- `input_data`: Maps metadata (search_term, location, business_name, category, address, phone, rating, review_count, lat, lng, cid, maps_url, website)
- `raw_domain`: Website domain from Maps listing (or resolved via Serper)
- `extracted_data`: Intel extraction results (same as Product 3)
- `contacts`: Contact enrichment results (same as Product 3)

## 5. CSV Output Format

**Filename:** `maps_intel_results_{YYYYMMDD_HHMMSS}.csv`

### Maps metadata columns (always present):

| Column | Source | Description |
|--------|--------|-------------|
| `search_term` | User input | Original search query |
| `location` | User input | Search location |
| `business_name` | Serper Maps | Business name from Google Maps |
| `category` | Serper Maps | Google Maps business category |
| `maps_address` | Serper Maps | Address from Maps listing |
| `maps_phone` | Serper Maps | Phone from Maps listing |
| `website` | Serper Maps / Resolved | Business website |
| `rating` | Serper Maps | Google rating (0-5) |
| `review_count` | Serper Maps | Total Google reviews |
| `latitude` | Serper Maps | GPS latitude |
| `longitude` | Serper Maps | GPS longitude |
| `google_maps_url` | Constructed | `https://www.google.com/maps/place/?cid={cid}` |
| `status` | Pipeline | Row processing status |

### Intel extraction columns (conditional, same as Product 3):

If `industry_description`: `industry`, `niche`, `description`, `address`, `phone`, `general_emails`
If `target_market`: `target_market`, `case_studies`
If `company_people`: `generic_emails`
If `homepage_raw_text`: `homepage_raw_text`

### Contact columns (if `company_people` enabled):

For i = 1 to max_contacts:
- `contact_{i}_title`, `contact_{i}_first_name`, `contact_{i}_last_name`
- `contact_{i}_email`, `contact_{i}_phone`, `contact_{i}_linkedin_url`

## 6. Frontend Architecture

### New Files

| File | Purpose |
|------|---------|
| `frontend/src/app/tools/maps-intel/page.tsx` | Main page component (4-step wizard) |
| `frontend/src/components/MapsSearchInput.tsx` | Search terms + location input component |

### Reused Components (unchanged)

- `ExtractionSettings.tsx` — extraction option checkboxes + contact config
- `EmailGate.tsx` — email capture form
- `ProgressTracker.tsx` — phase progress visualization (custom phase names)
- `LivePreview.tsx` — real-time results preview
- `ResultsPanel.tsx` — final results + CSV download

### Tool Registry Entry

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
}
```

### API Client Additions

```typescript
// In api.ts
export async function submitMapsExtraction(body: MapsExtractRequest, token: string)
export function getMapsDownloadUrl(jobId: string, token: string): string
```

### localStorage Keys

- `qe_maps_job_id`
- `qe_maps_token`

## 7. Constraints & Edge Cases

### Scraping Resistance
- Sites that block scraping: handled by Scrape.do with residential proxies (existing infrastructure)
- Google Maps itself: Serper handles all Maps scraping — we never touch Google directly

### Scale (50K+ businesses)
- Max 500 search term + location combos
- Max 100 results per combo (5 pages x 20 results)
- Max 50,000 total businesses per job
- Pipeline handles via batched queues with backpressure (existing architecture)
- Serper API handles volume at 300 QPS

### Deduplication
- Same business appears in multiple search terms -> deduplicate by normalized website domain
- Businesses without websites -> deduplicate by `business_name + search_location` (the location from the user's search query, avoiding address parsing)
- Keep the first occurrence's Maps metadata, merge search terms into comma-separated list

### Missing Websites
- ~10-20% of Maps listings lack a website
- For entries without website: attempt Serper web search using backend's Serper API key: `"{business_name}" {location} official website`
- If still no website: include in CSV with Maps-only data, mark status as `"no_website"`

### Rate Limiting
- Same per-email/IP rate limits as other products
- Serper Maps + resolve calls share existing `settings.serper_concurrency` semaphore (50 concurrent)

### Caching
- Serper Maps responses: 3-day TTL (same as G2 discovery)
- Website crawl results: 7-day TTL (existing)
- Intel extraction: 7-day TTL (existing)

## 8. Success Criteria

1. User can enter search terms + location and receive Google Maps business data
2. Businesses are enriched with structured intelligence (industry, target market, contacts) via existing pipeline
3. CSV download contains both Maps metadata and enriched intel
4. Pipeline handles 50K+ businesses without memory/timeout issues
5. Processing speed comparable to Products 3 & 4 (Maps discovery adds <5 minutes for 500 search term combos)
6. Zero new external API dependencies (Serper only)

## 9. Cost Analysis

For a typical job of 2,000 businesses (100 search terms x 20 results):
- Serper Maps queries: 100 x $0.001 = $0.10
- Website crawling: ~1,600 unique domains x Scrape.do credits
- LLM extraction: ~1,600 domains x Gemini API credits
- QuickEnrich enrichment: ~1,600 domains x API credits

Serper Maps cost is negligible compared to existing pipeline costs.
