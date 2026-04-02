# Product 6: Funded Companies Today — Design Spec

**Date:** 2026-04-01
**Status:** Draft
**Tool Slug:** `funding-intel`

## 1. Purpose

Show users a live list of companies that received funding in the last 24-48 hours. Users can browse, filter by round type, select companies, and then extract structured business intelligence (industry, target market, contacts) via the existing intel pipeline. This is "funding discovery" feeding into the Product 3 enrichment engine.

**Users:** Sales teams targeting newly funded companies, VCs doing competitive intel, recruiters, marketers.

## 2. Data Sources

### Primary: Serper `/news` Endpoint (already integrated)

**Why Serper over Google News RSS:**
- Already in the codebase (`backend/app/services/serper.py`) — same API key, same patterns
- Returns clean JSON (no XML parsing needed)
- Returns direct article URLs (not Google redirect URLs)
- Returns `snippet` field with more context for LLM extraction
- Cost: 1-3 credits per discovery run (~$0.003) — negligible

**Queries:** Three targeted queries run in parallel for broad coverage, each with `num=100`:
1. `startup "raises" funding`
2. `"Series A" OR "Series B" OR "Series C" funding round`
3. `"seed round" OR "pre-seed" startup funding`

Time filtering uses `tbs=qdr:d` parameter in the Serper request body (last 24 hours). For 48-hour mode, use `tbs=qdr:2d`. The `tbs` parameter is the standard Google time-range filter supported by Serper's news endpoint.

### Extraction: Gemini 2.5 Flash (already integrated)

LLM extracts structured fields from headlines/snippets:
- `company_name` (required)
- `funding_amount` (e.g., "$5.5M", "$291M", null if not stated)
- `funding_round` (Seed, Series A, Series B, etc., or Unknown)
- `lead_investor` (if mentioned, null otherwise)
- `description_snippet` (brief description of what the company does)
- `is_funding_round` (boolean — filters out acquisitions, grants, IPOs)

Batched at 15 headlines per LLM call. ~3-5 API calls for a full discovery run.

### Resolution: Serper `/search` (existing)

For companies without a website in the news article, the existing resolve phase uses Serper web search to find company domains.

## 3. User Flow (4-Step Wizard)

### Step 1: Discover Funding (`discover` phase)

When the user lands on the page:
1. Backend auto-fetches today's funding news (cached for 1 hour to avoid redundant API calls)
2. Displays a table of discovered companies with columns:
   - Company Name
   - Amount Raised
   - Round Type
   - Lead Investor
   - Description
   - Source (news article link)
3. Each row has a checkbox for selection
4. Filter pills at top: All, Seed, Series A, Series B, Series C+, Growth, Unknown
5. "Select All" / "Deselect All" buttons
6. Refresh button to re-fetch (respects 1-hour cache)

Users can also toggle between "Last 24 hours" and "Last 48 hours".

### Step 2: Extraction Settings (`configure` phase)

Reuses `ExtractionSettings` component:
- Industry & Description (default: checked)
- Target Market (default: checked)
- Company's People (default: checked)
- Homepage Raw Text (default: unchecked)

`hasCompanyNames` is `false` — backend uses its own Serper API key for website resolution since the funding discovery already happened server-side with the backend key. The `job.config` will not contain a `serper_api_key` field; the intel pipeline's resolve phase falls through to `settings.serper_api_key` when the config key is absent or empty (see `serper.py:50`: `api_key or settings.serper_api_key`).

### Step 3: Email Gate (`submit` phase)

Reuses `EmailGate` component. Summary:
> "Extract intel for {N} recently funded companies."

### Step 4: Processing (`processing` phase)

6-phase pipeline: **Discover → Resolve → Crawl → Extract → Enrich → Deliver**

Reuses `ProgressTracker`, `LivePreview`, `ResultsPanel`.

### Results Phase

CSV download with funding metadata + enriched intel.

## 4. Backend Architecture

### 4.1 New Files

| File | Purpose |
|------|---------|
| `backend/app/services/funding_discovery.py` | Fetch funding news via Serper + LLM extraction |
| `backend/app/workers/funding_pipeline.py` | Phase 0 discovery + delegate to intel pipeline |
| `backend/app/routers/funding.py` | API routes: GET `/funding/discover`, POST `/funding/extract`, GET `/funding/download/{job_id}` |

### 4.2 Modified Files

| File | Change |
|------|--------|
| `backend/app/main.py` | Import + register funding router, add pipeline to ARQ worker |
| `backend/app/workers/intel_pipeline.py:436` | Add `"funding-intel": "funding"` to `dl_slug_map` |
| `frontend/src/lib/api.ts` | Add funding API client functions |
| `frontend/src/lib/tool-registry.ts` | Add funding-intel tool config |
| `frontend/src/app/page.tsx` | Add funding-intel icon |

### 4.3 API Endpoints

**`GET /api/v1/funding/discover`**

No auth required. Returns cached list of today's funded companies.

Query params:
- `hours`: 24 or 48 (default: 24)

Response:
```json
{
  "companies": [
    {
      "company_name": "Anvil Robotics",
      "funding_amount": "$5.5M",
      "funding_round": "Seed",
      "lead_investor": "Sequoia Capital",
      "description_snippet": "Warehouse automation platform",
      "source_url": "https://techcrunch.com/...",
      "source_name": "TechCrunch"
    }
  ],
  "total": 35,
  "cached_at": "2026-04-01T14:30:00Z",
  "hours": 24
}
```

**`POST /api/v1/funding/extract`**

Auth required (email token).

Request body:
```json
{
  "companies": [
    {
      "company_name": "Anvil Robotics",
      "funding_amount": "$5.5M",
      "funding_round": "Seed",
      "lead_investor": "Sequoia Capital",
      "description_snippet": "Warehouse automation platform",
      "source_url": "https://techcrunch.com/...",
      "source_name": "TechCrunch"
    }
  ],
  "options": {
    "industry_description": true,
    "target_market": true,
    "company_people": true,
    "homepage_raw_text": false
  },
  "quickenrich_api_key": "",
  "job_titles": ["CEO", "Founder", "CTO"],
  "max_contacts": 3
}
```

Response:
```json
{
  "job_id": "uuid",
  "total_rows": 15,
  "token": "jwt_token"
}
```

**`GET /api/v1/funding/download/{job_id}?token=...`**
- Streams CSV with funding metadata + intel columns
- Filename: `funding_intel_results_{YYYYMMDD_HHMMSS}.csv`

### 4.4 Funding Discovery Service

`backend/app/services/funding_discovery.py`:

```
1. Run 3 Serper /news queries in parallel:
   - "startup raises funding"
   - "Series A OR Series B OR Series C funding round"
   - "seed round OR pre-seed startup funding"
   Each with tbs=qdr:d (or qdr:2d for 48h), num=100

2. Merge and deduplicate results by article URL

3. Batch headlines+snippets to Gemini (15 per batch):
   - Extract: company_name, funding_amount, funding_round, lead_investor, description_snippet, is_funding_round
   
4. Filter: keep only is_funding_round=true entries

5. Deduplicate by company_name (case-insensitive) — keep richest data

6. Cache result for 1 hour (funding_discovery:{hours}h)

7. Return list of structured funding entries
```

### 4.5 Pipeline Design

**Phase 0: Funding Discovery**

```
1. User selects companies from the discovery list
2. For each selected company:
   - Create JobResult with:
     - input_data: {
         input: company_name,
         input_type: "name",
         company_name, funding_amount, funding_round,
         lead_investor, description_snippet, source_url
       }
     - status: "pending"
3. Update job.total_rows
```

**Phases 1-5: Intel Pipeline Delegation**

Same as Products 4 and 5:
- All entries go through resolve phase (Serper web search to find company website)
- Then: Crawl → Extract → Enrich → Deliver

### 4.6 Database Usage

No schema changes. Uses existing tables:

**`jobs` table:**
- `tool_slug`: `"funding-intel"`
- `config`: `{"companies": [...], "options": {...}, ...}`
- `status`: `pending` → `funding_discovering` → `resolving` → `delivering` → `completed`

**`job_results` table:**
- `input_data`: Funding metadata (company_name, funding_amount, funding_round, lead_investor, description_snippet, source_url)
- `raw_domain`: Resolved via Serper web search
- `extracted_data`: Intel extraction results (same as Product 3)

## 5. CSV Output Format

**Filename:** `funding_intel_results_{YYYYMMDD_HHMMSS}.csv`

### Funding metadata columns (always present):

| Column | Source | Description |
|--------|--------|-------------|
| `company_name` | Discovery | Company that received funding |
| `funding_amount` | Discovery | Amount raised (e.g., "$5.5M") |
| `funding_round` | Discovery | Round type (Seed, Series A, etc.) |
| `lead_investor` | Discovery | Lead investor name |
| `funding_description` | Discovery | Brief description of company |
| `source_url` | Discovery | Link to news article |
| `source_name` | Discovery | Publication name (e.g., "TechCrunch") |
| `website` | Resolve | Company website domain |
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
| `frontend/src/app/tools/funding-intel/page.tsx` | Main page (4-step wizard) |
| `frontend/src/components/FundingDiscoveryPanel.tsx` | Funding company table with filters + selection |

### Reused Components (unchanged)

- `ExtractionSettings.tsx`
- `EmailGate.tsx`
- `ProgressTracker.tsx` (with `funding_discovering` phase alias)
- `LivePreview.tsx`
- `ResultsPanel.tsx`

### Tool Registry Entry

```typescript
{
  slug: "funding-intel",
  name: "Funded Companies Today",
  description:
    "Discover companies that received funding today and extract business intelligence, contacts, and more.",
  isActive: true,
  backendUrl: API_BASE_URL,
  requiredColumns: [],
  optionalColumns: [],
  columnPatterns: {},
}
```

### localStorage Keys

- `qe_funding_job_id`
- `qe_funding_token`

## 7. Constraints & Edge Cases

### Data Freshness
- Discovery results cached for 1 hour to balance freshness vs API cost
- Users can toggle 24h/48h window
- Refresh button bypasses cache (rate-limited to 1 per 5 minutes per IP using existing `rate_limits` table with action `funding_refresh`)

### LLM Extraction Accuracy
- Headlines with ambiguous funding info marked as `funding_round: "Unknown"`
- Acquisitions, IPOs, grants filtered via `is_funding_round` flag
- Deduplication by company name catches multiple articles about same round

### Scale
- Typical day: 30-50 funded companies after dedup
- Max: ~200 companies in a 48h window
- Well within existing pipeline capacity (handles 50K+)

### Missing Websites
- ~30-40% of newly funded startups may not have easily discoverable websites
- Serper web search handles most (same as Product 3's resolve phase)
- Entries without websites: included in CSV with funding-only data, status `"no_website"`

### International Coverage
- Google News RSS/Serper returns global funding news
- Non-English company names preserved as-is
- No country filtering (all funding rounds included)

## 8. Success Criteria

1. User sees a list of 30-50 recently funded companies within seconds of loading the page
2. Companies are filterable by round type
3. Selected companies get enriched with structured intelligence via existing pipeline
4. CSV download contains both funding metadata and enriched intel
5. Discovery data refreshes automatically every hour
6. Zero new API dependencies (uses Serper + Gemini, both already integrated)

## 9. Cost Analysis

Per discovery run (1 per hour cache):
- Serper /news queries: 3 x $0.001 = $0.003
- Gemini extraction: ~4 calls x ~$0.001 = $0.004
- Total discovery cost: ~$0.007 per run, ~$0.17/day

Per enrichment job (user-triggered):
- Serper resolve: ~30 queries x $0.001 = $0.03
- Website crawling: ~25 domains x Scrape.do credits
- LLM extraction: ~25 domains x Gemini credits
- QuickEnrich contacts: ~25 domains x API credits

Discovery cost is negligible. Enrichment cost is identical to Products 3-5.
