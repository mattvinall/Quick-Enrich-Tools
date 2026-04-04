# Product 7: People Intel — Design Spec

**Date:** 2026-04-04
**Slug:** `people-intel`
**Status:** Design approved, ready for implementation

## Summary

User uploads a list of people (name + company name or website). We search Serper for their LinkedIn profiles (`site:linkedin.com/in/ "name" "company"`), resolve the company website, then run the existing intel pipeline (crawl, extract, enrich, deliver). Output: LinkedIn URLs + structured company intelligence + optional contact enrichment.

**Success criteria:** User uploads people, receives LinkedIn URLs and structured business intelligence based on selected extraction options. Must handle 50K rows. Production-ready with unit and integration tests.

---

## Architecture

### Approach: LinkedIn Search + Company Intel Pipeline (Approach B)

Follows the G2 pattern: product-specific Phase 0 (LinkedIn discovery), then delegate to the existing intel pipeline for phases 1-5.

**Why this approach:**
- 90% of backend code already exists (intel pipeline, Serper, scraping, LLM extraction, enrichment)
- Only truly new code: LinkedIn search service + name parsing
- Proven pattern (G2 uses identical delegation architecture)
- Full value delivery: LinkedIn URLs + complete company intelligence

---

## Pipeline Phases

```
Phase 0: LINKEDIN SEARCH (new)
  Input: full_name + company_name per row
  Action: Serper query "site:linkedin.com/in/ {name} {company}"
  Output: linkedin_url stored in search_results JSONB
  Status: linkedin_searching → rows marked found/not_found

Phase 1: RESOLVE (reuse intel_pipeline._phase_resolve_worker)
  Input: company_name per row (or website if provided)
  Action: Serper search for company domain (skip if website provided)
  Output: raw_domain populated
  Optimization: Deduplicate by company_name — search each company once

Phase 2: CRAWL (reuse intel_pipeline._phase_crawl_worker)
  Input: resolved domains
  Action: Spider.cloud crawl homepage + relevant internal pages
  Output: scraped text in memory dict
  Optimization: Deduplicate by domain — crawl each domain once, fan out to all rows

Phase 3: EXTRACT (reuse intel_pipeline._phase_extract_worker)
  Input: scraped text per domain
  Action: LLM extraction (Gemini 2.5 Flash or GPT-4o-mini)
  Output: extracted_data JSONB (industry, niche, description, target_market, etc.)
  Optimization: Extract per domain, fan out to all rows with same domain

Phase 4: ENRICH (reuse intel_pipeline._phase_enrich_worker)
  Input: normalized domains + job titles
  Action: QuickEnrich API for additional contacts (optional)
  Output: contacts JSONB

Phase 5: DELIVER (reuse intel_pipeline deliver)
  Action: Send email with download link, mark job completed
```

### Company Deduplication (Critical for Scale)

If 500 people work at Apple, we:
- Search LinkedIn 500 times (unique per person — required)
- Resolve Apple's website ONCE
- Crawl apple.com ONCE
- Extract intel from apple.com ONCE
- Fan out the shared company data to all 500 rows

Implementation: After Phase 0, group rows by normalized company_name. For phases 1-3, process unique companies only. Map results back to all rows sharing that company.

---

## LinkedIn Search Service

### New file: `backend/app/services/linkedin_search.py`

**Core function:**
```python
async def search_linkedin_profile(
    client: httpx.AsyncClient,
    full_name: str,
    company_name: str,
    api_key: str | None = None,
) -> dict:
    """Search Serper for a person's LinkedIn profile."""
    query = f'site:linkedin.com/in/ "{full_name}" "{company_name}"'
    # POST https://google.serper.dev/search
    # Headers: X-API-KEY, Content-Type: application/json
    # Body: {"q": query, "num": 3}
    # Returns: {linkedin_url, confidence, query, results}
```

**Batch function:**
```python
async def batch_linkedin_search(
    rows: list[dict],
    concurrency: int = 50,
    api_key: str | None = None,
) -> list[dict]:
    """Batch search with deduplication and caching."""
    # Dedup by (full_name_lower, company_name_lower)
    # Semaphore-limited concurrency (default 50)
    # Redis cache: key = sha256("linkedin", name_lower, company_lower), TTL 7 days
    # Retry: 3 attempts, exponential backoff (reuse retry.py)
```

**LinkedIn URL extraction:**
- Filter Serper results for URLs matching `linkedin.com/in/`
- Pick first matching result (Google ranks by relevance)
- Strip query params and fragments from URL
- Normalize to `https://www.linkedin.com/in/{slug}`

**Confidence scoring:**
- 0.0: No results with linkedin.com/in/ URL
- 0.5: URL found but title doesn't contain person's name
- 0.8: URL found and title contains person's name
- 0.9: URL found, title contains name, snippet mentions company
- Store as float in search_results JSONB

**Edge cases:**
- No LinkedIn results → linkedin_url empty, confidence 0, status `not_found` for LinkedIn but still proceed to company resolve
- Common names → company name in query disambiguates; confidence score lets user filter
- Person not on LinkedIn → proceed with company enrichment anyway (still valuable)
- Unicode/international names → pass through as-is, Serper handles encoding
- Empty name or company → skip row, mark `failed` with error message

---

## Input & Data Model

### Input Modes

**Paste mode** — one person per line:
- `Fred Smith, Apple` (comma-separated)
- `Fred Smith | Apple Inc.` (pipe-separated)
- `Fred Smith - Apple` (dash-separated)
- Auto-detect separator: scan first 5 non-empty lines, pick most common separator from [`, `, ` | `, ` - `]
- Trim whitespace from both name and company
- Skip empty lines

**CSV mode** — upload CSV file:
- Auto-detect columns via regex patterns:
  - Full name: `/^(full.?name|name|person|contact)$/i`
  - First name: `/^(first.?name|fname|given.?name|first)$/i`
  - Last name: `/^(last.?name|lname|surname|family.?name|last)$/i`
  - Company: `/^(company|org|employer|business|firm|organization|company.?name)$/i`
  - Website (optional): `/^(website|url|domain|site|company.?url|company.?website)$/i`
- If first_name + last_name columns detected, concatenate with space
- If full_name column detected, use as-is
- Validation: must have name column(s) + company column
- Limits: 50MB max, 100K rows max (consistent with other products)

### JobResult Storage

Uses existing `job_results` table, no schema changes:

| Field | Content |
|-------|---------|
| `input_data` | `{full_name, company_name, website?, input_type: "paste"\|"csv"}` |
| `search_results` | `{linkedin_url, linkedin_confidence, linkedin_query, linkedin_results: [...], company_query?, company_results?: [...]}` |
| `raw_domain` | Company website domain (from resolve phase) |
| `verified_domain` | Not used (P2 only) |
| `normalized_domain` | Final clean company domain |
| `extracted_data` | LLM extraction output (reuse P3 schema) |
| `contacts` | QuickEnrich contacts (reuse P3 schema) |
| `status` | `pending → found/not_found → resolved → crawled → extracted → enriched` |

---

## Frontend

### Page: `/tools/people-intel/page.tsx`

5-phase wizard, identical structure to company-intel:

**Phase 1 — Input (dual-tab: Paste / Upload CSV)**
- Paste tab: `PeopleInputPanel.tsx` component
  - Textarea with placeholder: `"Fred Smith, Apple\nJane Doe, Google\nBob Jones, Microsoft"`
  - Stats display: total lines, parsed count, failed parse count
  - Format hint below textarea
- CSV tab: Reuse `UploadZone.tsx`
  - Column auto-detect for name + company
  - Manual column selector dropdowns
  - Support first_name + last_name OR full_name columns

**Phase 2 — Configure**
- Reuse `ExtractionSettings.tsx` exactly as-is
- Checkboxes: Industry & Description, Target Market, Company's People, Home Page Raw Text
- QuickEnrich API key + job titles + max contacts (if People enabled)
- Optional Serper API key field (user's own key)

**Phase 3 — Submit**
- Reuse `EmailGate.tsx`

**Phase 4 — Processing**
- Reuse `ProgressTracker.tsx`
- Pipeline phase labels: `LinkedIn Search → Resolve → Crawl → Extract → Enrich → Deliver`
- Reuse `LivePreview.tsx`
  - Columns: Name, Company, LinkedIn (clickable), Website, Status

**Phase 5 — Results**
- Reuse `ResultsPanel.tsx`
- Base columns: Full Name, Company Name, LinkedIn URL (clickable link), Website, Status
- Conditional columns based on extraction options (same as company-intel):
  - Industry, Niche (if Industry & Description)
  - Target Market (if Target Market)
  - Contact fields (if Company's People)
- Stat cards: Total Rows, LinkedIn Found, Companies Resolved, Match Rate %

### New Frontend Components

**`PeopleInputPanel.tsx`** (~80 lines)
- Similar to `IntelInputPanel.tsx` but parses "name, company" format
- Auto-detect separator
- Show parsed count and any parse failures
- Returns: `{items: [{full_name, company_name}], parseErrors: number}`

### Modified Frontend Files

- `tool-registry.ts` — add people-intel entry
- `api.ts` — add `submitPeopleExtraction()` and `getPeopleDownloadUrl()` functions
- `page.tsx` (home) — add icon (User + Search icons from Lucide)

---

## Backend API

### New router: `backend/app/routers/people.py`

**POST `/api/v1/people/extract`**
```python
class PeopleExtractionRequest(BaseModel):
    items: list[PeopleItem]  # [{full_name, company_name, website?}]
    options: ExtractionOptions  # {industry_description, target_market, company_people, homepage_raw_text}
    serper_api_key: str | None = None
    quickenrich_api_key: str | None = None
    job_titles: list[str] = ["CEO", "Founder"]
    max_contacts: int = 3

class PeopleItem(BaseModel):
    full_name: str
    company_name: str
    website: str | None = None
```

Validation:
- items must be non-empty
- items max 100,000
- At least one extraction option must be True
- full_name and company_name must be non-empty strings per item

Response: `{job_id: str, total_rows: int, token: str}`

**GET `/api/v1/people/download/{job_id}?token=...`**

Streaming CSV with columns:
```
Full Name, Company Name, LinkedIn URL, LinkedIn Confidence, Website, Status,
[Industry, Niche, Description — if industry_description],
[Target Market, Case Studies — if target_market],
[{Title} - Title, {Title} - First Name, {Title} - Last Name, {Title} - Email, {Title} - Phone, {Title} - LinkedIn — if company_people],
[Home Page Raw Text — if homepage_raw_text]
```

Pagination: 500-row batches for memory efficiency (consistent with other products).

---

## Pipeline Worker

### New file: `backend/app/workers/people_pipeline.py`

Follows G2 pattern:

```python
async def run_people_pipeline(ctx: dict, job_id: str) -> None:
    """People Intel pipeline: LinkedIn search + delegate to intel pipeline."""
    # 1. Update job status to 'linkedin_searching'
    # 2. Load all JobResult rows for this job
    # 3. Batch LinkedIn search (Phase 0)
    #    - batch_linkedin_search() with concurrency=50
    #    - Update each row's search_results with linkedin_url + confidence
    #    - Update row status: found/not_found
    #    - Update job progress
    # 4. Prepare for intel pipeline:
    #    - For rows without user-provided website: set input to company_name for resolve
    #    - For rows with website: set raw_domain directly (skip resolve)
    # 5. Delegate to run_intel_pipeline(ctx, job_id)
    #    - This handles phases 1-5 (Resolve → Crawl → Extract → Enrich → Deliver)
```

Register in `main.py`:
```python
from app.workers.people_pipeline import run_people_pipeline
# Add to all_functions list
```

---

## Database Migration

### `database/migrations/006_register_people_intel_tool.sql`

```sql
-- Register people-intel tool
INSERT INTO tools (id, slug, name, description, is_active)
VALUES (
  gen_random_uuid(),
  'people-intel',
  'People Intel by Name',
  'Upload names and company names to find LinkedIn profiles and extract business intelligence.',
  true
)
ON CONFLICT (slug) DO NOTHING;

-- Update jobs status constraint to include linkedin_searching
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_status_check;
ALTER TABLE jobs ADD CONSTRAINT jobs_status_check CHECK (
    status IN (
        'pending', 'completed', 'failed',
        'parsing', 'searching', 'verifying', 'normalizing', 'enriching', 'delivering',
        'resolving', 'crawling', 'extracting', 'crawled', 'extracted',
        'g2_scraping',
        'linkedin_searching'
    )
);
```

---

## Configuration

Add to `backend/app/config.py`:

```python
linkedin_search_concurrency: int = 50
people_pipeline_batch_size: int = 200
```

No new API keys — reuses existing Serper, Spider, Gemini/OpenAI, QuickEnrich, Resend.

---

## Testing Strategy

### Unit Tests

**`backend/tests/test_linkedin_search.py`**
- Query construction: name + company → correct Serper query string
- LinkedIn URL extraction: filter results for linkedin.com/in/ URLs
- URL normalization: strip query params, fragments, trailing slashes
- Confidence scoring: no results → 0, name match → 0.8, name + company → 0.9
- Cache key generation: consistent hashing for (name, company) pairs
- Deduplication: same (name, company) pair → single API call
- Edge cases: empty name, empty company, unicode characters, very long names

**`backend/tests/test_people_input_parsing.py`**
- Comma separator: `"Fred Smith, Apple"` → `{full_name: "Fred Smith", company_name: "Apple"}`
- Pipe separator: `"Fred Smith | Apple"` → same
- Dash separator: `"Fred Smith - Apple"` → same
- Auto-detect: mixed separators → pick most common
- Whitespace handling: leading/trailing spaces trimmed
- Empty lines: skipped
- Single field (no separator): mark as parse error
- Company with comma: `"Fred Smith, Apple, Inc."` → first comma splits name from company, remaining commas are part of company name ("Apple, Inc.")
- CSV column detection: various header patterns matched correctly

### Integration Tests

**`backend/tests/test_people_pipeline.py`**
- Full pipeline with mocked external services (Serper, Spider, LLM, QuickEnrich)
- LinkedIn found + company resolved → full enrichment flow
- LinkedIn not found → company still resolved and enriched
- Company deduplication: 5 people at same company → 1 crawl, 1 extract
- Mixed results: some found, some not → correct per-row statuses
- Error propagation: phase failure → job marked failed with error message
- Progress updates: phase_progress JSONB updated correctly at each phase
- Large batch: 1000 rows processed in micro-batches of 200

**`backend/tests/test_people_api.py`**
- POST /people/extract with valid payload → 200 + job_id + token
- POST with empty items → 422
- POST with no extraction options selected → 422
- POST with missing full_name → 422
- GET /people/download valid token → streaming CSV
- GET /people/download invalid token → 401
- GET /people/download incomplete job → 404

### Edge Cases Covered (80/20)

1. **Common names** → company name disambiguates in Serper query; confidence score lets user filter low-confidence matches
2. **Company name variations** ("Apple" vs "Apple Inc.") → Serper fuzzy matching handles this; company dedup normalizes names
3. **Person not on LinkedIn** → status `not_found` for LinkedIn, but company resolve + intel extraction proceeds
4. **Company website blocks scraping** → status `scrape_failed`, LinkedIn URL still returned in results
5. **Duplicate companies in batch** → deduplicate at resolve/crawl/extract; single crawl per domain
6. **50K rows** → micro-batching (200/batch), bounded queues (maxsize=5), company dedup, semaphore concurrency
7. **Empty/malformed input rows** → skip with `failed` status + error message
8. **Serper rate limiting** → retry with exponential backoff (3 attempts, 1s base), 429 handling
9. **User provides website instead of company name** → skip resolve phase, use website directly
10. **Mixed input: some with websites, some without** → route each row appropriately

---

## Files Summary

### New Files (10)

| File | Purpose |
|------|---------|
| `backend/app/services/linkedin_search.py` | LinkedIn Serper search service |
| `backend/app/routers/people.py` | API endpoints (extract + download) |
| `backend/app/workers/people_pipeline.py` | Pipeline worker (Phase 0 + delegate) |
| `frontend/src/app/tools/people-intel/page.tsx` | Tool page (5-phase wizard) |
| `frontend/src/components/PeopleInputPanel.tsx` | Paste input parser component |
| `database/migrations/006_register_people_intel_tool.sql` | Tool registration + status constraint |
| `backend/tests/test_linkedin_search.py` | LinkedIn search unit tests |
| `backend/tests/test_people_input_parsing.py` | Input parsing unit tests |
| `backend/tests/test_people_pipeline.py` | Pipeline integration tests |
| `backend/tests/test_people_api.py` | API endpoint tests |

### Modified Files (5)

| File | Change |
|------|--------|
| `backend/app/main.py` | Register people router + pipeline worker |
| `backend/app/config.py` | Add linkedin_search_concurrency, people_pipeline_batch_size |
| `frontend/src/lib/tool-registry.ts` | Add people-intel tool config |
| `frontend/src/lib/api.ts` | Add submitPeopleExtraction(), getPeopleDownloadUrl() |
| `frontend/src/app/page.tsx` | Add people-intel icon to TOOL_ICONS |
