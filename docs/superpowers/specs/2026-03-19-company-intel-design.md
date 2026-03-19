# Product 3: Company/People Intel by URL — Design Spec

**Date:** 2026-03-19
**Tool slug:** `company-intel`
**Status:** Design

---

## Overview

Users paste a list of company URLs or names (one per line). The system scrapes each company's website, uses a cheap LLM to extract structured business intelligence, and optionally enriches contacts via QuickEnrich API. Results are displayed in a table and downloadable as CSV.

**Key decision — Hybrid scraping + LLM extraction:** Pure LLM fails because models hallucinate company details for SMBs (stale training data). Pure regex/CSS-selector parsing is brittle across diverse website templates. The hybrid approach scrapes real website content with Scrape.do, then uses GPT-4o-mini (or Gemini 2.5 Flash) to extract structured data from the scraped text. Cost: ~$0.001/company. Accuracy: 95%+ on structured data. Real-time freshness.

---

## User Flow

```
Paste URLs/names → Select extraction options → Enter API keys (if needed) → Enter email → Run → Progress → Results
```

**Phases (frontend state machine):**

1. **input** — Textarea + Extraction Settings checkboxes + conditional API key fields
2. **submit** — Email capture + confirm (reuses existing EmailGate pattern)
3. **processing** — Progress tracker with SSE (reuses ProgressTracker + LivePreview)
4. **results** — Table + download CSV + Clay push (reuses ResultsPanel pattern)

---

## Frontend Design

### Page: `/tools/company-intel/page.tsx`

**Layout (input phase):**

```
┌─────────────────────────────────────────────────────────────────┐
│  🔍  Company/People Intel by URL          🏢 Company Intelligence │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Extract Deep Insights                                          │
│  Paste a list of URLs or company names (one per line).          │
│  We'll automatically determine if we need to search for the     │
│  website or scrape it directly to gather the intelligence       │
│  you need.                                                      │
│                                                                  │
│  ┌──────────────────────────┐   ┌────────────────────────────┐  │
│  │  apple.com               │   │ ⚙ Extraction Settings      │  │
│  │  Microsoft               │   │ Select data points to      │  │
│  │  https://stripe.com      │   │ retrieve.                  │  │
│  │                          │   │                            │  │
│  │                          │   │ ☑ Industry & Description   │  │
│  │                          │   │   Retrieves Industry,      │  │
│  │                          │   │   Niche, and a ~600 word   │  │
│  │                          │   │   company description.     │  │
│  │                          │   │                            │  │
│  │                          │   │ ☑ Target Market            │  │
│  │                          │   │   Identifies Target Market  │  │
│  │                          │   │   and extracts Case Studies │  │
│  │                          │   │   company names.           │  │
│  │                          │   │                            │  │
│  │                          │   │ ☑ Company's People         │  │
│  │                          │   │   Finds Contacts (name,    │  │
│  │                          │   │   title, email, phone) and │  │
│  │                          │   │   generic emails.          │  │
│  │                          │   │                            │  │
│  │                          │   │ ☐ Home Page Raw Text       │  │
│  │                          │   │   Returns the raw, viewable│  │
│  │                          │   │   text scraped from the    │  │
│  └──────────────────────────┘   │   home page.               │  │
│   42 lines detected              │                            │  │
│                                  │ ─────────────────────────  │  │
│                                  │ QuickEnrich.io API Key     │  │
│                                  │   (shown if People checked)│  │
│                                  │ [qe_...              ]     │  │
│                                  │ Get 50,000 free credits    │  │
│                                  │                            │  │
│                                  │ Serper API Key             │  │
│                                  │   (shown if names detected)│  │
│                                  │ [serper_...           ]    │  │
│                                  └────────────────────────────┘  │
│                                                                  │
│                        [ 🔍 Run Extraction ]                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Input Detection Logic

Each line is classified as URL or company name:
- **URL**: Contains `.` with a valid TLD pattern, or starts with `http://`/`https://`
- **Company name**: Everything else

The line counter shows: `42 lines detected` (or `12 URLs, 30 company names detected` if mixed).

If ANY company names are detected (not URLs), show the Serper API Key field with helper text: "Required to search for company websites from names."

If "Company's People" checkbox is selected, show the QuickEnrich API Key field.

### Extraction Settings (Checkboxes)

| Option | Default | What it extracts |
|--------|---------|-----------------|
| Industry & Description | ✅ ON | industry, niche, ~600 word description, address, phone, general emails |
| Target Market | ✅ ON | target market description, case study company names |
| Company's People | ✅ ON | contact names/titles from website + QuickEnrich enriched email/phone, generic emails (info@, etc.) |
| Home Page Raw Text | ☐ OFF | raw visible text from homepage |

### Submit Phase

After clicking "Run Extraction":
- Show email capture inline (same pattern as Product 2's EmailGate)
- Validate: at least one checkbox selected, textarea not empty, required API keys provided
- On submit: POST to backend, transition to processing phase

### Processing Phase

Reuse existing ProgressTracker with phases adapted for this pipeline:

```
Resolve → Crawl → Extract → Enrich → Deliver
```

- **Resolve**: Finding websites for company names (skipped if all URLs)
- **Crawl**: Scraping company websites
- **Extract**: LLM extracting structured intel
- **Enrich**: QuickEnrich contact enrichment (skipped if not selected)
- **Deliver**: Sending email with results

Live preview table shows results as they complete.

### Results Phase

Table columns (dynamic based on selected options):

**Always shown:**
- Input (original URL/name)
- Website (resolved domain)
- Status

**If Industry & Description:**
- Industry
- Niche
- Description (truncated, hover to expand)
- Address
- Phone
- General Emails

**If Target Market:**
- Target Market
- Case Studies (comma-separated company names)

**If Company's People:**
- Contact Name
- Contact Title
- Contact Email
- Contact Phone
- Contact LinkedIn
- Generic Emails

**If Homepage Raw Text:**
- Homepage Text (truncated in table, full in CSV)

**CSV output format:** One row per company. Contacts are flattened into sub-columns: `contact_1_name`, `contact_1_title`, `contact_1_email`, `contact_1_phone`, `contact_1_linkedin`, `contact_2_name`, etc. (up to 5 contacts per company, matching P2's pattern). If a company has multiple contacts, they expand horizontally. The results table shows only the first contact inline, with an expand/collapse to see additional contacts.

Download CSV includes all columns untruncated.

---

## Backend Architecture

### New Files

```
backend/app/
├── services/
│   ├── scraper.py          # Scrape.do integration + HTML→text extraction
│   └── intel_extractor.py  # LLM prompts for company intel extraction
├── workers/
│   └── intel_pipeline.py   # 5-phase pipeline for company intel
└── routers/
    └── intel.py            # Upload + download endpoints for company-intel tool
```

### Reused From Product 2

- `services/serper.py` — URL resolution for company names
- `services/enrichment.py` — QuickEnrich contact enrichment
- `services/cache.py` — Redis caching
- `services/retry.py` — Exponential backoff
- `services/email_service.py` — Resend delivery
- `services/llm/` — Gemini/OpenAI providers (extended with new prompts)
- `routers/email_capture.py` — Email capture + rate limiting
- `routers/jobs.py` — Job status + SSE + preview
- `auth.py` — JWT tokens
- `models.py` — Extended with new fields
- `config.py` — Extended with new settings

### New Config Settings

```python
# Scraping
scrape_do_api_key: str = ""
scrape_concurrency: int = 30        # concurrent Scrape.do requests
max_pages_per_site: int = 6         # homepage + 5 internal pages
scrape_timeout: int = 20            # seconds per page

# Intel extraction
intel_extraction_concurrency: int = 10   # concurrent LLM extraction calls
intel_llm_provider: str = "gemini"       # or "openai" — reuses existing toggle
```

### Database Changes

**New column on `job_results`:**

```sql
ALTER TABLE job_results ADD COLUMN extracted_data JSONB;
```

`extracted_data` stores all LLM-extracted intel:

```json
{
  "industry": "Dental Services",
  "niche": "Pediatric Dentistry",
  "description": "PB Dentistry is a family-focused dental practice...",
  "target_market": "Families with young children in the Palm Beach County area",
  "case_studies": ["Palm Beach Gardens Elementary", "Jupiter Medical Center"],
  "address": "123 Main St, West Palm Beach, FL 33401",
  "phone": "(561) 555-1234",
  "general_emails": ["info@pbdentistry.com", "appointments@pbdentistry.com"],
  "homepage_raw_text": "Welcome to PB Dentistry..."
}
```

Existing columns reused:
- `input_data` → `{input: "pbdentistry.com", input_type: "url"}` or `{input: "Microsoft", input_type: "name"}`
- `search_results` → Serper results (only for name→URL resolution)
- `raw_domain` → initial domain (from input or Serper)
- `normalized_domain` → final clean domain after redirect resolution
- `contacts` → QuickEnrich contact array (same schema as Product 2)
- `status` → row processing status

**New tool registration:**

```sql
INSERT INTO tools (id, slug, name, description, is_active)
VALUES (gen_random_uuid(), 'company-intel', 'Company/People Intel by URL',
  'Extract business intelligence from company websites. Upload URLs or company names to get industry, contacts, target market, and more.', true);
```

### API Endpoints

**New router: `/api/v1/intel/`**

| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| POST | `/intel/extract` | Bearer | Accept text input + config, create job, enqueue pipeline |
| GET | `/intel/download/{job_id}` | Bearer | Stream results CSV with intel columns |

**Reused endpoints (unchanged):**
- `POST /email-capture` — email capture
- `GET /jobs/{job_id}` — job status
- `GET /jobs/{job_id}/sse` — SSE progress
- `GET /jobs/{job_id}/preview` — live preview
- `POST /clay-push/{job_id}` — Clay integration

### POST `/intel/extract` Request Body

```json
{
  "lines": ["apple.com", "Microsoft", "https://stripe.com"],
  "options": {
    "industry_description": true,
    "target_market": true,
    "company_people": true,
    "homepage_raw_text": false
  },
  "serper_api_key": "optional - only if company names present",
  "quickenrich_api_key": "optional - only if company_people selected"
}
```

No CSV upload needed — just a JSON array of strings + config. Simpler than Product 2.

---

## Pipeline Architecture

### 5-Phase Pipeline: `intel_pipeline.py`

```
Phase 1: URL Resolution
    ↓ queue_rc (maxsize=5)
Phase 2: Site Crawl
    ↓ queue_ce (maxsize=5)
Phase 3: Intel Extraction
    ↓ queue_en (maxsize=5)
Phase 4: Contact Enrichment
    ↓
Phase 5: Delivery
```

Same bounded-queue + backpressure pattern as Product 2.

### Phase 1: URL Resolution

**For URL inputs:** Normalize domain (strip protocol, www, paths). Store in `raw_domain`.

**For company name inputs:** Call Serper API with user-provided key:
- Query: `"{company_name}" official website`
- Extract candidate domain from first result
- Store in `raw_domain` + `search_results`

**Concurrency:** `serper_concurrency` (50)
**Caching:** Same Redis cache as Product 2 (7-day TTL)
**Dedup:** Group by normalized input to avoid duplicate searches

### Phase 2: Site Crawl

**For each domain with `raw_domain` set:**

1. **Scrape homepage** via Scrape.do API:
   ```
   GET https://api.scrape.do/?token={SCRAPE_DO_API_KEY}&url=https://{domain}&render=false
   ```
   - `render=false` for speed (most company sites are server-rendered)
   - Fall back to `render=true` if response is too short (<500 chars)

2. **Discover relevant internal pages** from homepage HTML:
   - Parse all `<a href>` links
   - Filter to same-domain internal links
   - Score by URL pattern + anchor text relevance:
     - **High**: `/about`, `/about-us`, `/team`, `/our-team`, `/people`, `/leadership`, `/staff`, `/contact`, `/contact-us`
     - **Medium**: `/services`, `/products`, `/solutions`, `/what-we-do`
     - **Lower**: `/case-studies`, `/clients`, `/customers`, `/portfolio`, `/testimonials`, `/partners`, `/our-work`
   - Select top pages based on what the user wants to extract:
     - Industry & Description → prioritize about, services
     - Target Market → prioritize case-studies, clients, testimonials
     - Company's People → prioritize team, about, leadership, contact
   - Cap at `max_pages_per_site` (default 6 total including homepage)

3. **Scrape selected pages** (parallel, semaphore-limited)

4. **Extract visible text** from each page:
   - Parse HTML with BeautifulSoup
   - Remove: `<script>`, `<style>`, `<nav>`, `<footer>`, `<header>` (navigation)
   - Extract text from `<main>`, `<article>`, or `<body>` (in priority order)
   - Strip excessive whitespace
   - Truncate to ~8,000 chars per page (to stay within LLM context limits)

5. **Store combined text** in memory (passed to Phase 3 via queue, not stored in DB permanently — only the extracted structured data is persisted)

**Concurrency:** `scrape_concurrency` (30)
**Caching:** Redis cache by domain (7-day TTL) — cache the scraped text, not raw HTML
**Error handling:** If a page fails, continue with what we have. Homepage alone is enough for basic extraction.

### Phase 3: Intel Extraction (LLM)

Feed the combined scraped text to the LLM with a structured extraction prompt.

**Prompt template:**

```
You are a business intelligence analyst. Extract the following data points from this company's website content.

Company website: {domain}
Pages scraped: {page_urls}

--- WEBSITE CONTENT ---
{combined_text}
--- END CONTENT ---

Extract the following into a JSON object:
{dynamic_fields_based_on_options}

Rules:
- Only include information you can directly find or confidently infer from the provided text
- For description: Write a ~600 word professional description of the company based on the content
- For case_studies: Extract company/organization names mentioned as clients or in case studies
- For general_emails: Look for emails like info@, contact@, hello@, support@, sales@
- For address: Extract the full mailing/office address if found
- For phone: Extract the main company phone number if found
- For contacts: Extract names and titles of people mentioned on the website
- If a data point is not found in the content, set it to null
- Return valid JSON only
```

**Dynamic field selection based on user options:**
- Industry & Description → `industry`, `niche`, `description`, `address`, `phone`, `general_emails`
- Target Market → `target_market`, `case_studies`
- Company's People → `website_contacts` (names/titles found on site), `general_emails`
- Homepage Raw Text → `homepage_raw_text` (just pass through the homepage text, no LLM needed)

**LLM provider:** Reuse existing Gemini/OpenAI SDK clients directly in `intel_extractor.py`. This is a standalone extraction function — NOT added to `BaseLLMProvider` (which is scoped to P2's domain verification). The extractor calls the SDK directly based on `settings.llm_provider`.

**Token budget per company:** ~3,000-5,000 input tokens (scraped text) + ~500-1,000 output tokens.

**Batching:** One LLM call per company (unlike P2 which batches 20 domain verifications). Company intel extraction needs the full context per company.

**Concurrency:** `intel_extraction_concurrency` (10)
**Caching:** Redis cache by `domain + selected_options` (7-day TTL)

### Phase 4: Contact Enrichment

**Only runs if Company's People is selected AND QuickEnrich API key provided.**

Uses the user-provided QuickEnrich API key (not backend key).

1. Take contact names/titles found from website scraping (Phase 3 output `website_contacts`)
2. Call QuickEnrich API for the domain to get enriched contacts with verified email/phone
3. Merge: website-scraped contacts + QuickEnrich contacts
4. Deduplicate by email (or first_name + last_name if no email)
5. When overlap exists, prefer QuickEnrich data (verified email/phone)
6. Store merged contacts in `job_results.contacts`

**Reuses existing `enrichment.py` service** — refactored to accept an optional `api_key` parameter (defaults to `settings.quickenrich_api_key` for P2 backward compat). P3 passes the user-provided key.

**Same refactor needed for `serper.py`** — add optional `api_key` parameter to `search_company()` and `batch_search()`, defaulting to `settings.serper_api_key`. P3 passes the user-provided key for name resolution.

**Concurrency:** `enrich_concurrency` (30)
**Caching:** Redis cache by `domain + api_key_hash` (7-day TTL)

### Phase 5: Delivery

Same as Product 2:
- Calculate stats: total companies, data extracted, contacts enriched
- Send branded HTML email via Resend with download link
- Download link uses JWT token (7-day expiry)

---

## Scraper Service: `scraper.py`

```python
# Core functions:

async def scrape_page(client, url, scrape_do_api_key) -> str:
    """Scrape a single URL via Scrape.do, return HTML."""

async def extract_text_from_html(html: str) -> str:
    """Strip HTML to visible text using BeautifulSoup."""

async def discover_relevant_pages(html: str, domain: str, options: dict) -> list[str]:
    """Parse homepage HTML, find and score internal links, return top page URLs."""

async def crawl_site(client, domain, scrape_do_api_key, options, max_pages=6) -> dict[str, str]:
    """Crawl homepage + relevant pages. Returns {url: extracted_text}."""

async def batch_crawl(domains, scrape_do_api_key, options, concurrency=30) -> dict[str, dict]:
    """Crawl multiple domains concurrently with semaphore."""
```

**Dependencies:** `beautifulsoup4`, `httpx` (already installed), `lxml` (HTML parser, add to requirements).

---

## Intel Extractor Service: `intel_extractor.py`

```python
async def extract_company_intel(
    domain: str,
    scraped_pages: dict[str, str],
    options: dict,
) -> dict:
    """Use LLM to extract structured intel from scraped text.
    Calls Gemini/OpenAI SDK directly based on settings.llm_provider."""

async def batch_extract_intel(
    items: list[dict],  # [{domain, scraped_pages, options}]
    concurrency: int = 10,
) -> dict[str, dict]:
    """Extract intel for multiple companies concurrently."""
```

---

## Scale Considerations (50,000 companies)

| Phase | Operations | Concurrency | Est. Time | Est. Cost |
|-------|-----------|-------------|-----------|-----------|
| URL Resolution | 50K Serper calls (if all names) | 50 | ~30 min | User pays (Serper key) |
| Site Crawl | 50K × 5 pages = 250K scrape calls | 30 | ~4.5 hours | ~$99/mo Scrape.do Pro (250K exceeds Hobby plan) |
| Intel Extraction | 50K LLM calls | 10 | ~2.5 hours | ~$25 (GPT-4o-mini) |
| Contact Enrichment | 50K QuickEnrich calls | 30 | ~1 hour | User pays (QE key) |
| **Total** | | | **~8 hours** | **~$124 backend cost** |

Pipeline phases run concurrently (Phase 2 feeds Phase 3 as batches complete), so real wall time is closer to **5-6 hours** for 50K companies.

**Cost breakdown per company: ~$0.0025 backend cost** (scraping + LLM). Caching reduces this significantly for lists with duplicate domains. For typical jobs (500-5,000 companies), the Hobby plan ($29/mo, 250K requests) is sufficient.

---

## Caching Strategy

| Data | Cache Key | TTL | Benefit |
|------|-----------|-----|---------|
| Serper search | `serper:{hash(name, location)}` | 7 days | Dedup same company names |
| Scraped content | `scrape:{hash(domain)}` | 7 days | Avoid re-scraping same domain |
| Extracted intel | `intel:{hash(domain, options)}` | 7 days | Skip LLM if same domain+options |
| Contact enrichment | `enrich:{hash(domain, titles, max)}` | 7 days | Skip API if same query |

At 50K companies, dedup could reduce actual API calls by 30-60% (many lists have duplicate domains).

---

## Error Handling

- **Scrape.do failure** (blocked site, timeout): Mark row with scraped pages available. If only homepage scraped, extract from that. If nothing scraped, set status = "scrape_failed".
- **LLM extraction failure**: Retry 3x with backoff. On final failure, store partial data if available.
- **QuickEnrich failure**: Same as Product 2 — continue without contacts.
- **Serper failure**: Same as Product 2 — mark as "not_found".
- **Per-row isolation**: Individual row failures don't crash the pipeline.

---

## Frontend Component Reuse

| Component | Reuse | Changes |
|-----------|-------|---------|
| UI primitives (Button, Card, Input, Checkbox, Badge, etc.) | As-is | None |
| EmailGate | As-is | None |
| ProgressTracker | Modified | Different phase names/icons |
| LivePreview | Modified | Different columns |
| ResultsPanel | Modified | Dynamic columns based on options |
| ClayPushModal | As-is | None |
| useSSE hook | As-is | None |
| api.ts | Extended | New `submitExtraction()` + `downloadIntel()` functions |
| tool-registry.ts | Extended | Add company-intel tool config |

### New Components

- **IntelInputPanel** — Textarea with line counter + input type detection
- **ExtractionSettings** — Checkbox group with conditional API key fields
- These are specific to this tool's input phase (replaces UploadZone + ColumnMapper from P2)

---

## Tool Registry Addition

```typescript
{
  slug: "company-intel",
  name: "Company/People Intel by URL",
  description: "Extract business intelligence from company websites. Paste URLs or company names to get industry, contacts, target market, and more.",
  isActive: true,
  backendUrl: API_BASE_URL,
  requiredColumns: [],       // Not CSV-based
  optionalColumns: [],
  columnPatterns: {},
}
```

---

## Dependencies to Add

**Backend (`requirements.txt`):**
- `beautifulsoup4>=4.12.0` — HTML parsing
- `lxml>=5.0.0` — Fast HTML parser for BeautifulSoup

**Frontend (`package.json`):**
- No new dependencies needed

---

## File Summary

### New Files (9)

```
backend/app/services/scraper.py           # Scrape.do integration + HTML→text
backend/app/services/intel_extractor.py   # LLM structured extraction
backend/app/workers/intel_pipeline.py     # 5-phase pipeline
backend/app/routers/intel.py             # Extract + download endpoints
frontend/src/app/tools/company-intel/page.tsx        # Main tool page
frontend/src/components/IntelInputPanel.tsx           # Textarea + line detection
frontend/src/components/ExtractionSettings.tsx        # Checkboxes + API keys
database/migrations/002_add_extracted_data.sql        # Schema migration
database/migrations/003_register_company_intel_tool.sql  # Tool registration
```

### Modified Files (7)

```
backend/app/config.py               # Add scrape_do_api_key, scrape_concurrency, etc.
backend/app/main.py                 # Register new router, wire up intel pipeline worker
backend/app/models.py               # Add extracted_data column to JobResult
backend/app/services/serper.py      # Add optional api_key param to search_company/batch_search
backend/app/services/enrichment.py  # Add optional api_key param to enrich_company/batch_enrich
frontend/src/lib/tool-registry.ts   # Add company-intel tool
frontend/src/app/page.tsx           # Add icon for new tool
```

---

## Out of Scope

- User-provided LLM API keys (backend absorbs LLM cost — it's ~$0.001/company)
- Scrape.do API key from user (backend absorbs — it's ~$0.0002/company)
- PDF scraping (websites only)
- JavaScript-heavy SPA scraping (start with `render=false`, revisit if needed)
- Saved/recurring extraction jobs
- Bulk file upload (CSV) — input is textarea only per the spec
