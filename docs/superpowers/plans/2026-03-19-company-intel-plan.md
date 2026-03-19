# Company/People Intel by URL — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Product 3 — users paste URLs/company names, system scrapes websites and uses LLM to extract structured business intelligence (industry, contacts, target market, etc.)

**Architecture:** Hybrid scraping + LLM extraction. Scrape.do crawls company websites, then a cheap LLM (Gemini 2.5 Flash / GPT-4o-mini) extracts structured data from scraped text. 5-phase async pipeline (Resolve → Crawl → Extract → Enrich → Deliver) using same bounded-queue + backpressure pattern as Product 2. User-provided API keys for Serper (name resolution) and QuickEnrich (contacts).

**Tech Stack:** FastAPI, ARQ, SQLAlchemy (async), Redis, Scrape.do, Gemini/OpenAI, BeautifulSoup4, Next.js 14, Tailwind CSS, Framer Motion, Radix UI

**Spec:** `docs/superpowers/specs/2026-03-19-company-intel-design.md`

---

## File Map

### New Files
| File | Responsibility |
|------|---------------|
| `backend/app/services/scraper.py` | Scrape.do API integration, HTML→text extraction, page discovery, batch crawling |
| `backend/app/services/intel_extractor.py` | LLM prompt construction, structured JSON extraction from scraped text |
| `backend/app/workers/intel_pipeline.py` | 5-phase pipeline orchestrator for company intel jobs |
| `backend/app/routers/intel.py` | POST /intel/extract + GET /intel/download/{job_id} endpoints |
| `frontend/src/app/tools/company-intel/page.tsx` | Main tool page with 4-phase state machine |
| `frontend/src/components/IntelInputPanel.tsx` | Textarea with line counter + URL/name detection |
| `frontend/src/components/ExtractionSettings.tsx` | Checkbox group + conditional API key fields |
| `database/migrations/002_add_extracted_data.sql` | ALTER TABLE add extracted_data JSONB column |
| `database/migrations/003_register_company_intel_tool.sql` | INSERT tool record |

### Modified Files
| File | Changes |
|------|---------|
| `backend/app/config.py` | Add scrape_do_api_key, scrape_concurrency, max_pages_per_site, scrape_timeout, intel_extraction_concurrency |
| `backend/app/models.py` | Add extracted_data JSONB column to JobResult |
| `backend/app/main.py` | Register intel router, register intel pipeline in ARQ worker |
| `backend/app/services/serper.py` | Add optional api_key param to search_company and batch_search |
| `backend/app/services/enrichment.py` | Add optional api_key param to enrich_company and batch_enrich |
| `frontend/src/lib/api.ts` | Add submitExtraction() and getIntelDownloadUrl() functions |
| `frontend/src/lib/tool-registry.ts` | Add company-intel tool config |
| `frontend/src/app/page.tsx` | Add icon for company-intel tool |

---

## Task 1: Database Schema + Config + Model Changes

**Files:**
- Create: `database/migrations/002_add_extracted_data.sql`
- Create: `database/migrations/003_register_company_intel_tool.sql`
- Modify: `backend/app/config.py`
- Modify: `backend/app/models.py`

- [ ] **Step 1: Create the extracted_data migration**

Create `database/migrations/002_add_extracted_data.sql`:

```sql
ALTER TABLE job_results ADD COLUMN IF NOT EXISTS extracted_data JSONB;
```

- [ ] **Step 2: Create the tool registration migration**

Create `database/migrations/003_register_company_intel_tool.sql`:

```sql
INSERT INTO tools (id, slug, name, description, is_active)
VALUES (
  gen_random_uuid(),
  'company-intel',
  'Company/People Intel by URL',
  'Extract business intelligence from company websites. Upload URLs or company names to get industry, contacts, target market, and more.',
  true
)
ON CONFLICT (slug) DO NOTHING;
```

- [ ] **Step 3: Add new config settings**

Add these fields to `Settings` class in `backend/app/config.py` after line 31 (before `cache_ttl_days`):

```python
    scrape_do_api_key: str = ""
    scrape_concurrency: int = 30
    max_pages_per_site: int = 6
    scrape_timeout: int = 20
    intel_extraction_concurrency: int = 10
```

- [ ] **Step 4: Add extracted_data column to JobResult model**

Add this line to `JobResult` class in `backend/app/models.py` after line 82 (after `contacts`):

```python
    extracted_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
```

- [ ] **Step 5: Commit**

```bash
git add database/migrations/002_add_extracted_data.sql database/migrations/003_register_company_intel_tool.sql backend/app/config.py backend/app/models.py
git commit -m "feat(intel): add database schema, config, and model changes for company intel tool"
```

---

## Task 2: Refactor serper.py and enrichment.py for User-Provided API Keys

**Files:**
- Modify: `backend/app/services/serper.py`
- Modify: `backend/app/services/enrichment.py`

- [ ] **Step 1: Add optional api_key param to search_company**

In `backend/app/services/serper.py`, change the `search_company` function signature (line 23) and the header line (line 49):

```python
async def search_company(
    client: httpx.AsyncClient,
    company_name: str,
    location: str = "",
    api_key: str | None = None,
) -> dict[str, object]:
```

Replace the headers dict (line 48-50):
```python
        headers={
            "X-API-KEY": api_key or settings.serper_api_key,
            "Content-Type": "application/json",
        },
```

- [ ] **Step 2: Add optional api_key param to batch_search**

In `backend/app/services/serper.py`, change `batch_search` signature (line 82):

```python
async def batch_search(
    rows: list[dict[str, object]],
    concurrency: int | None = None,
    api_key: str | None = None,
) -> list[dict[str, object]]:
```

Update the lambda in `_search_one` (line 110) to pass api_key:

```python
                    result = await retry_async(
                        lambda cn=company_name, loc=location: search_company(client, cn, loc, api_key=api_key),
                        max_retries=3,
                        base_delay=1.0,
                    )
```

- [ ] **Step 3: Add optional api_key param to enrich_company**

In `backend/app/services/enrichment.py`, change `enrich_company` signature (line 21):

```python
async def enrich_company(
    client: httpx.AsyncClient,
    domain: str,
    job_titles: list[str],
    max_contacts: int = 1,
    api_key: str | None = None,
) -> list[dict[str, str]]:
```

Update the Authorization header in `_do_request` (line 44):

```python
            headers={"Authorization": f"Bearer {api_key or settings.quickenrich_api_key}"},
```

- [ ] **Step 4: Add optional api_key param to batch_enrich**

In `backend/app/services/enrichment.py`, change `batch_enrich` signature (line 100):

```python
async def batch_enrich(
    domains_with_rows: dict[str, list[int]],
    job_titles: list[str],
    max_contacts: int = 1,
    concurrency: int | None = None,
    api_key: str | None = None,
) -> dict[str, list[dict[str, str]]]:
```

Update `_enrich_one` to pass api_key (line 115):

```python
                    result = await enrich_company(client, domain, job_titles, max_contacts, api_key=api_key)
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/serper.py backend/app/services/enrichment.py
git commit -m "refactor: add optional api_key param to serper and enrichment services"
```

---

## Task 3: Scraper Service (Scrape.do + HTML→Text)

**Files:**
- Create: `backend/app/services/scraper.py`

- [ ] **Step 1: Create scraper.py with all functions**

Create `backend/app/services/scraper.py`:

```python
"""Scrape.do integration — crawl company websites and extract visible text."""

import asyncio
import logging
import re
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.services.cache import cache_get, cache_set, make_cache_key
from app.services.retry import retry_async

logger = logging.getLogger(__name__)

_MAX_TEXT_PER_PAGE = 8_000

# Page URL patterns scored by relevance category
_HIGH_PATTERNS = re.compile(
    r"/(about|about-us|team|our-team|people|leadership|staff|contact|contact-us)(/|$)", re.I
)
_MEDIUM_PATTERNS = re.compile(
    r"/(services|products|solutions|what-we-do|offerings)(/|$)", re.I
)
_LOW_PATTERNS = re.compile(
    r"/(case-stud|clients|customers|portfolio|testimonials|partners|our-work|success-stories)(/|$)", re.I
)

# Option-to-priority mapping: which URL patterns matter for each extraction option
_OPTION_PRIORITIES = {
    "industry_description": [_HIGH_PATTERNS, _MEDIUM_PATTERNS],
    "target_market": [_LOW_PATTERNS, _MEDIUM_PATTERNS],
    "company_people": [_HIGH_PATTERNS],
    "homepage_raw_text": [],
}


async def scrape_page(
    client: httpx.AsyncClient,
    url: str,
    render: bool = False,
) -> str:
    """Scrape a single URL via Scrape.do API. Returns raw HTML string."""
    encoded_url = url
    params = {
        "token": settings.scrape_do_api_key,
        "url": encoded_url,
    }
    if render:
        params["render"] = "true"

    response = await retry_async(
        lambda: client.get(
            "https://api.scrape.do",
            params=params,
            timeout=settings.scrape_timeout,
        ),
        max_retries=2,
        base_delay=1.0,
    )
    response.raise_for_status()
    return response.text


def extract_text_from_html(html: str) -> str:
    """Strip HTML to visible text using BeautifulSoup.

    Removes scripts, styles, nav, footer, header elements.
    Extracts from <main>, <article>, or <body> in priority order.
    Truncates to _MAX_TEXT_PER_PAGE characters.
    """
    soup = BeautifulSoup(html, "lxml")

    # Remove non-content elements
    for tag in soup.find_all(["script", "style", "nav", "footer", "header", "noscript", "svg"]):
        tag.decompose()

    # Try to find main content area
    content = soup.find("main") or soup.find("article") or soup.find("body")
    if content is None:
        content = soup

    text = content.get_text(separator="\n", strip=True)

    # Collapse excessive whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)

    return text[:_MAX_TEXT_PER_PAGE]


def discover_relevant_pages(
    html: str,
    domain: str,
    options: dict,
    max_pages: int = 5,
) -> list[str]:
    """Parse homepage HTML and return top internal page URLs sorted by relevance.

    Scores links by URL pattern matching against selected extraction options.
    Returns at most max_pages URLs (not including homepage).
    """
    soup = BeautifulSoup(html, "lxml")
    base_url = f"https://{domain}"

    scored: dict[str, int] = {}
    seen_paths: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        full_url = urljoin(base_url, href)

        parsed = urlparse(full_url)
        # Only same-domain internal links
        link_domain = parsed.netloc.removeprefix("www.")
        if link_domain != domain and link_domain != f"www.{domain}":
            continue

        path = parsed.path.rstrip("/")
        if not path or path == "/" or path in seen_paths:
            continue

        # Skip non-page resources
        if any(path.endswith(ext) for ext in (".pdf", ".jpg", ".png", ".gif", ".css", ".js", ".zip")):
            continue

        seen_paths.add(path)
        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

        score = 0
        for option_key, patterns in _OPTION_PRIORITIES.items():
            if not options.get(option_key, False):
                continue
            for i, pattern in enumerate(patterns):
                if pattern.search(path):
                    score += (3 - i)  # Higher score for higher priority patterns

        if score > 0:
            scored[clean_url] = max(scored.get(clean_url, 0), score)

    # Sort by score descending, take top max_pages
    sorted_urls = sorted(scored.keys(), key=lambda u: scored[u], reverse=True)
    return sorted_urls[:max_pages]


async def crawl_site(
    client: httpx.AsyncClient,
    domain: str,
    options: dict,
    max_pages: int | None = None,
) -> dict[str, str]:
    """Crawl a company website: homepage + relevant internal pages.

    Returns dict of {url: extracted_text}.
    """
    if max_pages is None:
        max_pages = settings.max_pages_per_site

    result: dict[str, str] = {}
    homepage_url = f"https://{domain}"

    # Step 1: Scrape homepage
    try:
        homepage_html = await scrape_page(client, homepage_url, render=False)

        # Fallback to render=true if content too short
        homepage_text = extract_text_from_html(homepage_html)
        if len(homepage_text) < 500:
            try:
                homepage_html = await scrape_page(client, homepage_url, render=True)
                homepage_text = extract_text_from_html(homepage_html)
            except Exception:
                pass  # Keep the original short text

        result[homepage_url] = homepage_text
    except Exception as exc:
        logger.warning("Failed to scrape homepage for %s: %s", domain, exc)
        return result

    # Step 2: Discover and scrape internal pages
    internal_urls = discover_relevant_pages(
        homepage_html, domain, options, max_pages=max_pages - 1
    )

    if internal_urls:
        sem = asyncio.Semaphore(5)  # Limit concurrency per site

        async def _scrape_internal(url: str) -> tuple[str, str]:
            async with sem:
                try:
                    html = await scrape_page(client, url, render=False)
                    return url, extract_text_from_html(html)
                except Exception as exc:
                    logger.debug("Failed to scrape %s: %s", url, exc)
                    return url, ""

        tasks = [_scrape_internal(u) for u in internal_urls]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)

        for outcome in outcomes:
            if isinstance(outcome, BaseException):
                continue
            url, text = outcome
            if text:
                result[url] = text

    return result


async def batch_crawl(
    domains: list[str],
    options: dict,
    concurrency: int | None = None,
) -> dict[str, dict[str, str]]:
    """Crawl multiple company websites concurrently.

    Returns {domain: {url: text}} for each domain.
    Checks Redis cache first; caches results for cache_ttl_days.
    """
    limit = concurrency if concurrency is not None else settings.scrape_concurrency
    semaphore = asyncio.Semaphore(limit)

    results: dict[str, dict[str, str]] = {}

    async with httpx.AsyncClient() as client:

        async def _crawl_one(domain: str) -> tuple[str, dict[str, str]]:
            # Check cache
            cache_key = make_cache_key("scrape", domain.lower())
            cached = await cache_get(cache_key)
            if cached is not None and isinstance(cached, dict):
                logger.info("SCRAPE CACHE HIT: %s", domain)
                return domain, cached

            async with semaphore:
                pages = await crawl_site(client, domain, options)
                if pages:
                    await cache_set(cache_key, pages, settings.cache_ttl_days)
                return domain, pages

        tasks = [_crawl_one(d) for d in domains]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)

    for outcome in outcomes:
        if isinstance(outcome, BaseException):
            logger.warning("batch_crawl error: %s", outcome)
            continue
        domain, pages = outcome
        results[domain] = pages

    return results
```

- [ ] **Step 2: Add dependencies to requirements.txt**

Append to `backend/requirements.txt`:

```
beautifulsoup4>=4.12.0
lxml>=5.0.0
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/scraper.py backend/requirements.txt
git commit -m "feat(intel): add Scrape.do service with HTML-to-text extraction and smart page discovery"
```

---

## Task 4: Intel Extractor Service (LLM Structured Extraction)

**Files:**
- Create: `backend/app/services/intel_extractor.py`

- [ ] **Step 1: Create intel_extractor.py**

Create `backend/app/services/intel_extractor.py`:

```python
"""LLM-based company intelligence extraction from scraped website content."""

import asyncio
import json
import logging

from app.config import settings
from app.services.cache import cache_get, cache_set, make_cache_key
from app.services.retry import retry_async

logger = logging.getLogger(__name__)


def _build_field_instructions(options: dict) -> str:
    """Build the dynamic field extraction instructions based on user options."""
    fields: list[str] = []

    if options.get("industry_description"):
        fields.extend([
            '"industry": string — the company\'s primary industry (e.g., "Healthcare", "SaaS", "Manufacturing")',
            '"niche": string — the company\'s specific niche within that industry',
            '"description": string — a ~600 word professional description of the company based on the website content',
            '"address": string or null — the company\'s physical address if found',
            '"phone": string or null — the company\'s main phone number if found',
            '"general_emails": list of strings — generic emails found (info@, contact@, hello@, support@, sales@, etc.)',
        ])

    if options.get("target_market"):
        fields.extend([
            '"target_market": string — description of who the company serves / their ideal customer',
            '"case_studies": list of strings — company or organization names mentioned as clients, partners, or in case studies',
        ])

    if options.get("company_people"):
        fields.extend([
            '"website_contacts": list of objects — people found on the website, each with "name" and "title" fields',
            '"general_emails": list of strings — generic emails found (info@, contact@, hello@, support@, sales@, etc.)',
        ])

    return "\n".join(f"  - {f}" for f in fields)


def _build_prompt(domain: str, scraped_pages: dict[str, str], options: dict) -> str:
    """Build the full extraction prompt for the LLM."""
    page_urls = list(scraped_pages.keys())
    combined_text = "\n\n---\n\n".join(
        f"[Page: {url}]\n{text}" for url, text in scraped_pages.items()
    )

    field_instructions = _build_field_instructions(options)

    return f"""You are a business intelligence analyst. Extract structured data from this company's website content.

Company website: {domain}
Pages scraped: {', '.join(page_urls)}

--- WEBSITE CONTENT ---
{combined_text}
--- END CONTENT ---

Extract the following fields into a JSON object:
{field_instructions}

Rules:
- Only include information you can directly find or confidently infer from the provided text.
- For "description": Write a ~600 word professional description of the company based on the content. Focus on what they do, who they serve, and their value proposition.
- For "case_studies": Extract company/organization names mentioned as clients or in case studies/testimonials. Return as a flat list of strings.
- For "general_emails": Look for emails like info@, contact@, hello@, support@, sales@. Do NOT include personal employee emails.
- For "address": Extract the full mailing/office address if found.
- For "phone": Extract the main company phone number if found.
- For "website_contacts": Extract names and titles of people mentioned on the website (team page, about page, etc.). Each entry should have "name" (string) and "title" (string).
- If a data point is not found in the content, set it to null (or empty list for list fields).
- Return ONLY valid JSON. No markdown, no explanation, just the JSON object."""


async def _call_gemini(prompt: str) -> dict:
    """Call Gemini API directly for intel extraction."""
    import google.generativeai as genai

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")

    response = await asyncio.to_thread(
        model.generate_content,
        prompt,
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json",
            temperature=0.1,
        ),
    )
    return json.loads(response.text)


async def _call_openai(prompt: str) -> dict:
    """Call OpenAI API directly for intel extraction."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.1,
    )
    content = response.choices[0].message.content or "{}"
    return json.loads(content)


async def extract_company_intel(
    domain: str,
    scraped_pages: dict[str, str],
    options: dict,
) -> dict:
    """Extract structured company intelligence from scraped website text.

    Uses LLM (Gemini or OpenAI) based on settings.llm_provider.
    Checks cache first. Returns extracted data dict.
    """
    # Check cache
    option_str = json.dumps(options, sort_keys=True)
    cache_key = make_cache_key("intel", domain.lower(), option_str)
    cached = await cache_get(cache_key)
    if cached is not None:
        logger.info("INTEL CACHE HIT: %s", domain)
        return cached

    if not scraped_pages:
        return {}

    prompt = _build_prompt(domain, scraped_pages, options)

    try:
        if settings.llm_provider == "openai":
            result = await retry_async(
                lambda: _call_openai(prompt),
                max_retries=3,
                base_delay=1.0,
            )
        else:
            result = await retry_async(
                lambda: _call_gemini(prompt),
                max_retries=3,
                base_delay=1.0,
            )

        await cache_set(cache_key, result, settings.cache_ttl_days)
        return result

    except Exception as exc:
        logger.warning("extract_company_intel failed for %s: %s", domain, exc)
        return {}


async def batch_extract_intel(
    items: list[dict],
    concurrency: int | None = None,
) -> dict[str, dict]:
    """Extract intel for multiple companies concurrently.

    Each item: {"domain": str, "scraped_pages": dict, "options": dict}
    Returns {domain: extracted_data_dict}.
    """
    limit = concurrency if concurrency is not None else settings.intel_extraction_concurrency
    semaphore = asyncio.Semaphore(limit)

    results: dict[str, dict] = {}

    async def _extract_one(item: dict) -> tuple[str, dict]:
        domain = item["domain"]
        async with semaphore:
            data = await extract_company_intel(
                domain, item["scraped_pages"], item["options"]
            )
            return domain, data

    tasks = [_extract_one(item) for item in items]
    outcomes = await asyncio.gather(*tasks, return_exceptions=True)

    for outcome in outcomes:
        if isinstance(outcome, BaseException):
            logger.warning("batch_extract_intel error: %s", outcome)
            continue
        domain, data = outcome
        results[domain] = data

    return results
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/intel_extractor.py
git commit -m "feat(intel): add LLM-based company intelligence extraction service"
```

---

## Task 5: Intel Pipeline Worker (5-Phase Orchestrator)

**Files:**
- Create: `backend/app/workers/intel_pipeline.py`

- [ ] **Step 1: Create intel_pipeline.py**

Create `backend/app/workers/intel_pipeline.py`:

```python
"""ARQ worker — 5-phase pipeline for company intelligence extraction.

Phases: Resolve → Crawl → Extract → Enrich → Deliver
Uses bounded asyncio.Queue for backpressure between phases.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

import tldextract
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import EmailCapture, Job, JobResult
from app.services.cache import make_cache_key, cache_get
from app.services.email_service import send_results_email
from app.services.enrichment import batch_enrich
from app.services.scraper import batch_crawl
from app.services.intel_extractor import batch_extract_intel
from app.services.serper import batch_search

logger = logging.getLogger(__name__)

QueueItem = list[uuid.UUID] | None


def _classify_input(line: str) -> tuple[str, str]:
    """Classify a line as 'url' or 'name' and return (input_type, cleaned_value).

    URL: contains a dot with valid TLD, or starts with http(s)://
    Name: everything else
    """
    stripped = line.strip()
    if not stripped:
        return "name", stripped

    # Explicit protocol
    if stripped.lower().startswith("http://") or stripped.lower().startswith("https://"):
        return "url", stripped

    # Check for domain-like pattern (has dot + valid TLD)
    ext = tldextract.extract(stripped)
    if ext.domain and ext.suffix:
        return "url", stripped

    return "name", stripped


def _extract_domain_from_url(url: str) -> str:
    """Extract clean domain from a URL string."""
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


async def update_job_progress(
    db: AsyncSession,
    job_id: uuid.UUID,
    phase: str,
    done: int,
    total: int,
    processed_rows: int | None = None,
) -> None:
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one()
    job.current_phase = phase
    job.phase_progress = {"done": done, "total": total}
    if processed_rows is not None:
        job.processed_rows = processed_rows
    await db.commit()


# ---------------------------------------------------------------------------
# Phase 1: URL Resolution
# ---------------------------------------------------------------------------

async def _phase_resolve_worker(
    job_id: uuid.UUID,
    total_rows: int,
    config: dict,
    queue_out: asyncio.Queue[QueueItem],
    error_event: asyncio.Event,
    progress: dict[str, int],
) -> None:
    """Resolve company names to domains via Serper; normalize URL inputs."""
    batch_size = settings.pipeline_batch_size
    serper_api_key = config.get("serper_api_key") or None

    try:
        async with AsyncSessionLocal() as db:
            for batch_start in range(0, total_rows, batch_size):
                if error_event.is_set():
                    break

                result = await db.execute(
                    select(JobResult)
                    .where(JobResult.job_id == job_id)
                    .order_by(JobResult.row_index)
                    .offset(batch_start)
                    .limit(batch_size)
                )
                batch_results = list(result.scalars().all())
                if not batch_results:
                    break

                # Separate URLs from names
                name_rows = []
                for r in batch_results:
                    input_type = (r.input_data or {}).get("input_type", "name")
                    raw_input = (r.input_data or {}).get("input", "")

                    if input_type == "url":
                        # Direct URL — extract domain
                        domain = _extract_domain_from_url(raw_input)
                        r.raw_domain = domain if domain else None
                        r.status = "resolved"
                    else:
                        # Company name — needs Serper search
                        name_rows.append({
                            "row_index": r.row_index,
                            "company_name": raw_input,
                            "location": "",
                        })

                # Batch search company names via Serper
                if name_rows:
                    search_outcomes = await batch_search(
                        name_rows, api_key=serper_api_key
                    )
                    outcome_by_idx = {int(o["row_index"]): o for o in search_outcomes}

                    result_by_row = {r.row_index: r for r in batch_results}
                    for i, row in enumerate(name_rows):
                        original_idx = row["row_index"]
                        job_result = result_by_row.get(original_idx)
                        if job_result is None:
                            continue
                        outcome = outcome_by_idx.get(i)
                        if outcome:
                            job_result.search_results = outcome.get("search_results")
                            candidate = outcome.get("candidate_domain", "")
                            job_result.raw_domain = str(candidate) if candidate else None
                        job_result.status = "resolved"

                await db.commit()

                ids = [r.id for r in batch_results]
                await queue_out.put(ids)

                done = min(batch_start + batch_size, total_rows)
                progress["resolve"] = done
                await update_job_progress(db, job_id, "resolve", done, total_rows, processed_rows=done)

    except Exception as exc:
        logger.exception("phase_resolve_worker failed: %s", exc)
        error_event.set()
        raise
    finally:
        await queue_out.put(None)


# ---------------------------------------------------------------------------
# Phase 2: Site Crawl
# ---------------------------------------------------------------------------

async def _phase_crawl_worker(
    job_id: uuid.UUID,
    total_rows: int,
    config: dict,
    queue_in: asyncio.Queue[QueueItem],
    queue_out: asyncio.Queue[QueueItem],
    error_event: asyncio.Event,
    progress: dict[str, int],
    scraped_data: dict[str, dict[str, str]],
) -> None:
    """Crawl company websites using Scrape.do."""
    options = config.get("options", {})

    try:
        async with AsyncSessionLocal() as db:
            total_crawled = 0

            while True:
                if error_event.is_set():
                    break

                msg = await queue_in.get()
                if msg is None:
                    break

                result_ids: list[uuid.UUID] = msg

                result = await db.execute(
                    select(JobResult).where(JobResult.id.in_(result_ids))
                )
                batch_results = list(result.scalars().all())

                # Collect unique domains to crawl
                domains_to_crawl: list[str] = []
                for r in batch_results:
                    if r.raw_domain and r.raw_domain not in scraped_data:
                        if r.raw_domain not in domains_to_crawl:
                            domains_to_crawl.append(r.raw_domain)

                # Batch crawl new domains
                if domains_to_crawl:
                    crawl_results = await batch_crawl(domains_to_crawl, options)
                    scraped_data.update(crawl_results)

                # Update status
                for r in batch_results:
                    if r.raw_domain and r.raw_domain in scraped_data:
                        r.status = "crawled"
                        # Store homepage raw text if requested
                        if options.get("homepage_raw_text"):
                            pages = scraped_data.get(r.raw_domain, {})
                            homepage_url = f"https://{r.raw_domain}"
                            homepage_text = pages.get(homepage_url, "")
                            if not r.extracted_data:
                                r.extracted_data = {}
                            r.extracted_data["homepage_raw_text"] = homepage_text
                    elif not r.raw_domain:
                        r.status = "not_found"
                    else:
                        r.status = "scrape_failed"

                await db.commit()

                total_crawled += len(batch_results)
                progress["crawl"] = total_crawled
                await update_job_progress(db, job_id, "crawl", total_crawled, total_rows)

                await queue_out.put(result_ids)

    except Exception as exc:
        logger.exception("phase_crawl_worker failed: %s", exc)
        error_event.set()
        raise
    finally:
        await queue_out.put(None)


# ---------------------------------------------------------------------------
# Phase 3: Intel Extraction (LLM)
# ---------------------------------------------------------------------------

async def _phase_extract_worker(
    job_id: uuid.UUID,
    total_rows: int,
    config: dict,
    queue_in: asyncio.Queue[QueueItem],
    queue_out: asyncio.Queue[QueueItem],
    error_event: asyncio.Event,
    progress: dict[str, int],
    scraped_data: dict[str, dict[str, str]],
) -> None:
    """Extract structured intel from scraped content using LLM."""
    options = config.get("options", {})
    # Only call LLM if at least one non-raw-text option is selected
    needs_llm = any(options.get(k) for k in ("industry_description", "target_market", "company_people"))

    try:
        async with AsyncSessionLocal() as db:
            total_extracted = 0

            while True:
                if error_event.is_set():
                    break

                msg = await queue_in.get()
                if msg is None:
                    break

                result_ids: list[uuid.UUID] = msg

                result = await db.execute(
                    select(JobResult).where(JobResult.id.in_(result_ids))
                )
                batch_results = list(result.scalars().all())

                if needs_llm:
                    # Build extraction items for domains that have scraped data
                    items: list[dict] = []
                    domain_to_results: dict[str, list[JobResult]] = {}

                    for r in batch_results:
                        if r.raw_domain and r.raw_domain in scraped_data:
                            if r.raw_domain not in domain_to_results:
                                domain_to_results[r.raw_domain] = []
                                items.append({
                                    "domain": r.raw_domain,
                                    "scraped_pages": scraped_data[r.raw_domain],
                                    "options": options,
                                })
                            domain_to_results[r.raw_domain].append(r)

                    if items:
                        intel_by_domain = await batch_extract_intel(items)

                        for domain, job_results in domain_to_results.items():
                            intel = intel_by_domain.get(domain, {})
                            for r in job_results:
                                existing = r.extracted_data or {}
                                existing.update(intel)
                                r.extracted_data = existing
                                r.normalized_domain = r.raw_domain
                                r.status = "extracted"

                    # Mark rows without scraped data
                    for r in batch_results:
                        if r.status not in ("extracted", "not_found"):
                            if r.raw_domain:
                                r.normalized_domain = r.raw_domain
                                r.status = "extracted"
                            else:
                                r.status = "not_found"
                else:
                    # No LLM needed — just pass through
                    for r in batch_results:
                        if r.raw_domain:
                            r.normalized_domain = r.raw_domain
                            r.status = "extracted"

                await db.commit()

                total_extracted += len(batch_results)
                progress["extract"] = total_extracted
                await update_job_progress(db, job_id, "extract", total_extracted, total_rows)

                await queue_out.put(result_ids)

    except Exception as exc:
        logger.exception("phase_extract_worker failed: %s", exc)
        error_event.set()
        raise
    finally:
        await queue_out.put(None)


# ---------------------------------------------------------------------------
# Phase 4: Contact Enrichment
# ---------------------------------------------------------------------------

async def _phase_enrich_worker(
    job_id: uuid.UUID,
    total_rows: int,
    config: dict,
    queue_in: asyncio.Queue[QueueItem],
    error_event: asyncio.Event,
    progress: dict[str, int],
    completion_event: asyncio.Event,
) -> None:
    """Enrich contacts via QuickEnrich API (optional)."""
    options = config.get("options", {})
    enrich_people = options.get("company_people", False)
    quickenrich_api_key = config.get("quickenrich_api_key") or None

    try:
        async with AsyncSessionLocal() as db:
            total_enriched = 0

            while True:
                if error_event.is_set():
                    break

                msg = await queue_in.get()
                if msg is None:
                    break

                result_ids: list[uuid.UUID] = msg

                if not enrich_people or not quickenrich_api_key:
                    total_enriched += len(result_ids)
                    progress["enrich"] = total_enriched
                    continue

                result = await db.execute(
                    select(JobResult).where(JobResult.id.in_(result_ids))
                )
                batch_results = list(result.scalars().all())

                # Group by domain for enrichment
                domains_with_rows: dict[str, list[int]] = {}
                for r in batch_results:
                    if r.normalized_domain:
                        domains_with_rows.setdefault(r.normalized_domain, []).append(r.row_index)

                if domains_with_rows:
                    # Get website contacts from extracted_data to use as job titles
                    # Use generic titles for QuickEnrich search
                    job_titles = ["CEO", "Founder", "Owner", "President", "Managing Director"]

                    contacts_by_domain = await batch_enrich(
                        domains_with_rows,
                        job_titles=job_titles,
                        max_contacts=5,
                        api_key=quickenrich_api_key,
                    )

                    result_by_row = {r.row_index: r for r in batch_results}
                    for domain, row_indices in domains_with_rows.items():
                        contacts = contacts_by_domain.get(domain, [])
                        for row_index in row_indices:
                            job_result = result_by_row.get(row_index)
                            if job_result is not None:
                                job_result.contacts = contacts
                                job_result.status = "enriched"

                    await db.commit()

                total_enriched += len(result_ids)
                progress["enrich"] = total_enriched
                await update_job_progress(db, job_id, "enrich", total_enriched, total_rows)

    except Exception as exc:
        logger.exception("phase_enrich_worker failed: %s", exc)
        error_event.set()
        raise
    finally:
        completion_event.set()


# ---------------------------------------------------------------------------
# Phase 5: Delivery
# ---------------------------------------------------------------------------

async def _phase_deliver(job_id: uuid.UUID) -> None:
    """Send results email to the user."""
    async with AsyncSessionLocal() as db:
        job_result = await db.execute(select(Job).where(Job.id == job_id))
        job = job_result.scalar_one()

        result = await db.execute(
            select(JobResult).where(JobResult.job_id == job_id)
        )
        all_results = list(result.scalars().all())
        extracted_count = sum(1 for r in all_results if r.extracted_data)
        contacts_count = sum(1 for r in all_results if r.contacts and len(r.contacts) > 0)

        email_capture_result = await db.execute(
            select(EmailCapture).where(EmailCapture.id == job.email_capture_id)
        )
        email_capture = email_capture_result.scalar_one()

        from app.auth import create_token
        download_token = create_token(email_capture.email, str(job_id))
        download_url = f"{settings.backend_url}/api/v1/intel/download/{job_id}?token={download_token}"

        job_stats = {
            "total_rows": job.total_rows,
            "websites_found": extracted_count,
            "contacts_enriched": contacts_count,
        }

        try:
            send_results_email(
                to_email=email_capture.email,
                download_url=download_url,
                job_stats=job_stats,
            )
        except Exception:
            logger.exception("Failed to send intel results email for job_id=%s", job_id)

        await update_job_progress(db, job_id, "deliver", 1, 1)


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

async def run_intel_pipeline(ctx: dict, job_id: str) -> None:
    """Main ARQ entry point for company intel extraction pipeline."""
    parsed_job_id = uuid.UUID(job_id)

    async with AsyncSessionLocal() as db:
        job_result = await db.execute(select(Job).where(Job.id == parsed_job_id))
        job = job_result.scalar_one()
        total_rows = job.total_rows
        config = job.config or {}

        job.status = "resolving"
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

    # Bounded queues for backpressure
    queue_rc: asyncio.Queue[QueueItem] = asyncio.Queue(maxsize=5)
    queue_ce: asyncio.Queue[QueueItem] = asyncio.Queue(maxsize=5)
    queue_en: asyncio.Queue[QueueItem] = asyncio.Queue(maxsize=5)

    error_event = asyncio.Event()
    completion_event = asyncio.Event()
    progress = {"resolve": 0, "crawl": 0, "extract": 0, "enrich": 0}

    # Shared scraped data (populated by crawl, consumed by extract)
    scraped_data: dict[str, dict[str, str]] = {}

    tasks = [
        asyncio.create_task(
            _phase_resolve_worker(parsed_job_id, total_rows, config, queue_rc, error_event, progress),
            name="phase_resolve",
        ),
        asyncio.create_task(
            _phase_crawl_worker(parsed_job_id, total_rows, config, queue_rc, queue_ce, error_event, progress, scraped_data),
            name="phase_crawl",
        ),
        asyncio.create_task(
            _phase_extract_worker(parsed_job_id, total_rows, config, queue_ce, queue_en, error_event, progress, scraped_data),
            name="phase_extract",
        ),
        asyncio.create_task(
            _phase_enrich_worker(parsed_job_id, total_rows, config, queue_en, error_event, progress, completion_event),
            name="phase_enrich",
        ),
    ]

    try:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                raise r

        async with AsyncSessionLocal() as db:
            job_result = await db.execute(select(Job).where(Job.id == parsed_job_id))
            job = job_result.scalar_one()
            job.status = "delivering"
            await db.commit()

        await _phase_deliver(parsed_job_id)

        async with AsyncSessionLocal() as db:
            job_result = await db.execute(select(Job).where(Job.id == parsed_job_id))
            job = job_result.scalar_one()
            job.status = "completed"
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()

        logger.info("Intel pipeline completed for job_id=%s", job_id)

    except Exception as exc:
        logger.exception("Intel pipeline failed for job_id=%s: %s", job_id, exc)
        error_event.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

        try:
            async with AsyncSessionLocal() as db:
                err_result = await db.execute(select(Job).where(Job.id == parsed_job_id))
                failed_job = err_result.scalar_one()
                failed_job.status = "failed"
                failed_job.error_message = str(exc)
                await db.commit()
        except Exception:
            logger.exception("Failed to mark intel job as failed for job_id=%s", job_id)
        raise
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/workers/intel_pipeline.py
git commit -m "feat(intel): add 5-phase pipeline worker for company intel extraction"
```

---

## Task 6: Intel Router (API Endpoints)

**Files:**
- Create: `backend/app/routers/intel.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create intel.py router**

Create `backend/app/routers/intel.py`:

```python
"""API endpoints for the Company/People Intel by URL tool."""

import csv
import io
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Annotated

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_token, verify_token
from app.config import settings
from app.database import get_db
from app.models import Job, JobResult

router = APIRouter(prefix="/intel", tags=["intel"])


class ExtractionOptions(BaseModel):
    industry_description: bool = True
    target_market: bool = True
    company_people: bool = True
    homepage_raw_text: bool = False


class ExtractRequest(BaseModel):
    lines: list[str]
    options: ExtractionOptions
    serper_api_key: str = ""
    quickenrich_api_key: str = ""


@router.post("/extract")
async def submit_extraction(
    body: ExtractRequest,
    token_payload: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Accept a list of URLs/company names and start the intel extraction pipeline."""
    import tldextract

    # Filter empty lines
    lines = [line.strip() for line in body.lines if line.strip()]
    if not lines:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No valid lines provided.",
        )

    if len(lines) > settings.max_rows:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Maximum {settings.max_rows} lines allowed.",
        )

    # Check at least one option selected
    opts = body.options
    if not any([opts.industry_description, opts.target_market, opts.company_people, opts.homepage_raw_text]):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one extraction option must be selected.",
        )

    # Classify each line as URL or name
    has_names = False
    parsed_lines = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Detect URL vs name
        is_url = False
        if stripped.lower().startswith("http://") or stripped.lower().startswith("https://"):
            is_url = True
        else:
            ext = tldextract.extract(stripped)
            if ext.domain and ext.suffix:
                is_url = True

        input_type = "url" if is_url else "name"
        if input_type == "name":
            has_names = True

        parsed_lines.append({
            "row_index": i,
            "input": stripped,
            "input_type": input_type,
        })

    # Validate: if company names present, Serper API key required
    if has_names and not body.serper_api_key:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Serper API key is required when company names (not URLs) are included.",
        )

    # Validate: if company_people selected, QuickEnrich API key required
    if opts.company_people and not body.quickenrich_api_key:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="QuickEnrich API key is required when Company's People option is selected.",
        )

    email = str(token_payload["sub"])
    email_capture_id = str(token_payload.get("job_id", ""))

    # Create Job
    job_config = {
        "options": opts.model_dump(),
        "serper_api_key": body.serper_api_key,
        "quickenrich_api_key": body.quickenrich_api_key,
    }

    job = Job(
        email_capture_id=uuid.UUID(email_capture_id),
        tool_slug="company-intel",
        status="pending",
        total_rows=len(parsed_lines),
        config=job_config,
    )
    db.add(job)
    await db.flush()

    # Create JobResult rows
    job_results = [
        JobResult(
            job_id=job.id,
            row_index=pl["row_index"],
            input_data={"input": pl["input"], "input_type": pl["input_type"]},
            status="pending",
        )
        for pl in parsed_lines
    ]
    db.add_all(job_results)
    await db.flush()

    # Dispatch to ARQ
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    redis_pool = await create_pool(redis_settings)
    try:
        await redis_pool.enqueue_job("run_intel_pipeline", str(job.id))
    finally:
        await redis_pool.aclose()

    new_token = create_token(email, str(job.id))
    return {
        "job_id": str(job.id),
        "total_rows": len(parsed_lines),
        "token": new_token,
    }


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

_BATCH_SIZE = 500
_BASE_COLUMNS = ["input", "website", "status"]

_INTEL_COLUMNS = [
    "industry", "niche", "description", "target_market", "case_studies",
    "address", "phone", "general_emails", "homepage_raw_text",
]
_CONTACT_FIELDS = ["Title", "First Name", "Last Name", "Email", "Phone", "LinkedIn"]


def _extract_intel_row(result: JobResult, options: dict, max_contacts: int = 5) -> list[str]:
    input_data = result.input_data or {}
    extracted = result.extracted_data or {}

    original_input = input_data.get("input", "")
    website = result.normalized_domain or result.raw_domain or ""
    row_status = result.status

    base = [original_input, website, row_status]

    # Intel columns based on options
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
        # Website contacts from LLM extraction
        website_contacts = extracted.get("website_contacts") or []
        generic_emails = extracted.get("general_emails") or []
        if not isinstance(generic_emails, list):
            generic_emails = []
        intel_cells.append(", ".join(generic_emails))

    if options.get("homepage_raw_text"):
        intel_cells.append(str(extracted.get("homepage_raw_text") or ""))

    # Contact columns (from QuickEnrich enrichment)
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


def _build_intel_headers(options: dict, max_contacts: int = 5) -> list[str]:
    headers = list(_BASE_COLUMNS)

    if options.get("industry_description"):
        headers.extend(["industry", "niche", "description", "address", "phone", "general_emails"])

    if options.get("target_market"):
        headers.extend(["target_market", "case_studies"])

    if options.get("company_people"):
        headers.append("generic_emails")

    if options.get("homepage_raw_text"):
        headers.append("homepage_raw_text")

    # Contact columns
    for i in range(1, max_contacts + 1):
        for field in _CONTACT_FIELDS:
            headers.append(f"contact_{i}_{field.lower().replace(' ', '_')}")

    return headers


async def _stream_intel_csv(job: Job, db: AsyncSession) -> AsyncGenerator[bytes, None]:
    yield b"\xef\xbb\xbf"  # UTF-8 BOM

    config = job.config or {}
    options = config.get("options", {})

    headers = _build_intel_headers(options)

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
            writer.writerow(_extract_intel_row(result, options))
        yield buf.getvalue().encode("utf-8")

        if len(rows) < _BATCH_SIZE:
            break
        offset += _BATCH_SIZE


@router.get("/download/{job_id}")
async def download_intel_results(
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
    filename = f"company_intel_results_{timestamp}.csv"

    return StreamingResponse(
        _stream_intel_csv(job, db),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

- [ ] **Step 2: Register the router and pipeline in main.py**

In `backend/app/main.py`, add the import (after line 19):

```python
from app.routers import intel
```

Add the router inclusion (after line 71):

```python
app.include_router(intel.router, prefix="/api/v1")
```

Update `_run_arq_worker` to import both pipeline modules. Replace lines 22-34:

```python
async def _run_arq_worker() -> None:
    """Start the ARQ worker in-process."""
    from arq import Worker
    from app.workers.pipeline import WorkerSettings as P2WorkerSettings
    from app.workers.intel_pipeline import run_intel_pipeline

    # Combine functions from both pipelines
    all_functions = list(P2WorkerSettings.functions) + [run_intel_pipeline]

    worker = Worker(
        functions=all_functions,
        redis_settings=P2WorkerSettings.redis_settings,
        max_jobs=P2WorkerSettings.max_jobs,
        job_timeout=P2WorkerSettings.job_timeout,
    )
    logger.info("ARQ worker starting in-process")
    await worker.async_run()
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/intel.py backend/app/main.py
git commit -m "feat(intel): add extract/download API endpoints and register pipeline in ARQ worker"
```

---

## Task 7: Frontend — API Client + Tool Registry

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/lib/tool-registry.ts`
- Modify: `frontend/src/app/page.tsx`

- [ ] **Step 1: Add submitExtraction and getIntelDownloadUrl to api.ts**

Append to `frontend/src/lib/api.ts`:

```typescript

export interface ExtractionOptions {
  industry_description: boolean;
  target_market: boolean;
  company_people: boolean;
  homepage_raw_text: boolean;
}

export interface ExtractRequest {
  lines: string[];
  options: ExtractionOptions;
  serper_api_key: string;
  quickenrich_api_key: string;
}

export interface ExtractResponse {
  job_id: string;
  total_rows: number;
  token: string;
}

export function submitExtraction(
  body: ExtractRequest,
  token: string,
): Promise<ExtractResponse> {
  return fetchAPI<ExtractResponse>(`${API_URL}/api/v1/intel/extract`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  });
}

export function getIntelDownloadUrl(jobId: string, token: string): string {
  return `${API_URL}/api/v1/intel/download/${jobId}?token=${encodeURIComponent(token)}`;
}
```

- [ ] **Step 2: Add company-intel to tool-registry.ts**

Add to the `tools` array in `frontend/src/lib/tool-registry.ts` (after the existing entry, before the closing `];`):

```typescript
  {
    slug: "company-intel",
    name: "Company/People Intel by URL",
    description:
      "Extract business intelligence from company websites. Paste URLs or company names to get industry, contacts, target market, and more.",
    isActive: true,
    backendUrl: API_BASE_URL,
    requiredColumns: [],
    optionalColumns: [],
    columnPatterns: {},
  },
```

- [ ] **Step 3: Add icon to homepage**

In `frontend/src/app/page.tsx`, add to the `TOOL_ICONS` object (after line 14):

```typescript
  "company-intel": (
    <div className="flex items-center gap-1 text-primary">
      <Search className="w-5 h-5" />
      <Users className="w-4 h-4" />
    </div>
  ),
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/lib/tool-registry.ts frontend/src/app/page.tsx
git commit -m "feat(intel): add frontend API client functions and tool registry entry"
```

---

## Task 8: Frontend — IntelInputPanel Component

**Files:**
- Create: `frontend/src/components/IntelInputPanel.tsx`

- [ ] **Step 1: Create IntelInputPanel.tsx**

Create `frontend/src/components/IntelInputPanel.tsx`:

```tsx
"use client";

import { useState, useCallback } from "react";

interface LineStats {
  total: number;
  urls: number;
  names: number;
}

interface IntelInputPanelProps {
  value: string;
  onChange: (value: string) => void;
  lineStats: LineStats;
}

function classifyLine(line: string): "url" | "name" {
  const trimmed = line.trim().toLowerCase();
  if (!trimmed) return "name";
  if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) return "url";
  // Check for domain-like pattern: has a dot with text on both sides
  const dotIdx = trimmed.indexOf(".");
  if (dotIdx > 0 && dotIdx < trimmed.length - 1) {
    // Simple TLD check — common TLDs
    const afterDot = trimmed.slice(dotIdx + 1).split(/[/?#]/)[0];
    if (afterDot.length >= 2 && afterDot.length <= 10 && /^[a-z]+$/.test(afterDot)) {
      return "url";
    }
  }
  return "name";
}

export function computeLineStats(text: string): LineStats {
  const lines = text.split("\n").filter((l) => l.trim());
  let urls = 0;
  let names = 0;
  for (const line of lines) {
    if (classifyLine(line) === "url") urls++;
    else names++;
  }
  return { total: lines.length, urls, names };
}

export default function IntelInputPanel({ value, onChange, lineStats }: IntelInputPanelProps) {
  return (
    <div className="space-y-2">
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={"apple.com\nMicrosoft\nhttps://stripe.com\nAcme Inc"}
        rows={14}
        className="w-full px-4 py-3 text-sm font-mono border border-border rounded-xl bg-white text-text-primary placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary/40 resize-y min-h-[200px]"
      />
      <div className="flex items-center gap-3 text-xs text-text-secondary">
        <span className="font-medium">
          {lineStats.total} {lineStats.total === 1 ? "line" : "lines"} detected
        </span>
        {lineStats.total > 0 && lineStats.urls > 0 && lineStats.names > 0 && (
          <span className="text-gray-400">
            ({lineStats.urls} {lineStats.urls === 1 ? "URL" : "URLs"},{" "}
            {lineStats.names} {lineStats.names === 1 ? "company name" : "company names"})
          </span>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/IntelInputPanel.tsx
git commit -m "feat(intel): add IntelInputPanel component with URL/name detection"
```

---

## Task 9: Frontend — ExtractionSettings Component

**Files:**
- Create: `frontend/src/components/ExtractionSettings.tsx`

- [ ] **Step 1: Create ExtractionSettings.tsx**

Create `frontend/src/components/ExtractionSettings.tsx`:

```tsx
"use client";

import { Settings, ExternalLink } from "lucide-react";

interface ExtractionSettingsProps {
  industryDescription: boolean;
  targetMarket: boolean;
  companyPeople: boolean;
  homepageRawText: boolean;
  onIndustryDescriptionChange: (v: boolean) => void;
  onTargetMarketChange: (v: boolean) => void;
  onCompanyPeopleChange: (v: boolean) => void;
  onHomepageRawTextChange: (v: boolean) => void;
  quickenrichApiKey: string;
  onQuickenrichApiKeyChange: (v: string) => void;
  serperApiKey: string;
  onSerperApiKeyChange: (v: string) => void;
  showSerperKey: boolean;
}

interface CheckboxItemProps {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  description: string;
}

function CheckboxItem({ checked, onChange, label, description }: CheckboxItemProps) {
  return (
    <label className="flex items-start gap-3 cursor-pointer group">
      <div className="pt-0.5">
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
          className="w-4 h-4 rounded border-gray-300 text-primary focus:ring-primary/50 cursor-pointer"
        />
      </div>
      <div className="space-y-0.5">
        <span className="text-sm font-semibold text-text-primary group-hover:text-primary transition-colors">
          {label}
        </span>
        <p className="text-xs text-text-secondary leading-relaxed">{description}</p>
      </div>
    </label>
  );
}

export default function ExtractionSettings({
  industryDescription,
  targetMarket,
  companyPeople,
  homepageRawText,
  onIndustryDescriptionChange,
  onTargetMarketChange,
  onCompanyPeopleChange,
  onHomepageRawTextChange,
  quickenrichApiKey,
  onQuickenrichApiKeyChange,
  serperApiKey,
  onSerperApiKeyChange,
  showSerperKey,
}: ExtractionSettingsProps) {
  return (
    <div className="rounded-xl border border-border bg-white p-5 space-y-5">
      {/* Header */}
      <div className="flex items-center gap-2">
        <Settings className="w-4 h-4 text-text-secondary" />
        <h3 className="text-sm font-semibold text-text-primary">Extraction Settings</h3>
      </div>
      <p className="text-xs text-text-secondary -mt-3">
        Select the data points you want to retrieve.
      </p>

      {/* Checkboxes */}
      <div className="space-y-4">
        <CheckboxItem
          checked={industryDescription}
          onChange={onIndustryDescriptionChange}
          label="Industry & Description"
          description="Retrieves Industry, Niche, and a ~600 word company description."
        />
        <CheckboxItem
          checked={targetMarket}
          onChange={onTargetMarketChange}
          label="Target Market"
          description="Identifies Target Market and extracts Case Studies company names."
        />
        <CheckboxItem
          checked={companyPeople}
          onChange={onCompanyPeopleChange}
          label="Company's People"
          description="Finds Contacts (name, title, email, phone) and generic emails."
        />
        <CheckboxItem
          checked={homepageRawText}
          onChange={onHomepageRawTextChange}
          label="Home Page Raw Text"
          description="Returns the raw, viewable text scraped from the home page."
        />
      </div>

      {/* Conditional API Key Fields */}
      {companyPeople && (
        <div className="space-y-1.5 pt-2 border-t border-border">
          <div className="flex items-center justify-between">
            <label className="text-xs font-semibold text-text-primary">
              QuickEnrich.io API Key
            </label>
            <a
              href="https://app.quickenrich.io"
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs font-medium text-primary hover:underline flex items-center gap-1"
            >
              Get Key <ExternalLink className="w-3 h-3" />
            </a>
          </div>
          <input
            type="text"
            value={quickenrichApiKey}
            onChange={(e) => onQuickenrichApiKeyChange(e.target.value)}
            placeholder="qe_..."
            className="w-full px-3 py-2 text-sm border border-border rounded-md bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
          />
          <p className="text-xs text-primary">
            Get 50,000 free QuickEnrich.io credits
          </p>
        </div>
      )}

      {showSerperKey && (
        <div className="space-y-1.5 pt-2 border-t border-border">
          <label className="text-xs font-semibold text-text-primary">
            Serper API Key
          </label>
          <input
            type="text"
            value={serperApiKey}
            onChange={(e) => onSerperApiKeyChange(e.target.value)}
            placeholder="serper_..."
            className="w-full px-3 py-2 text-sm border border-border rounded-md bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
          />
          <p className="text-xs text-text-secondary">
            Required to search for company websites from names.
          </p>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/ExtractionSettings.tsx
git commit -m "feat(intel): add ExtractionSettings component with checkboxes and API key fields"
```

---

## Task 10: Frontend — Main Tool Page

**Files:**
- Create: `frontend/src/app/tools/company-intel/page.tsx`

- [ ] **Step 1: Create the company-intel page**

Create `frontend/src/app/tools/company-intel/page.tsx`:

```tsx
'use client';

import { useState, useEffect, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Search, Building2 } from 'lucide-react';
import { Button } from '@/components/ui/button';

import IntelInputPanel, { computeLineStats } from '@/components/IntelInputPanel';
import ExtractionSettings from '@/components/ExtractionSettings';
import EmailGate from '@/components/EmailGate';
import ProgressTracker from '@/components/ProgressTracker';
import LivePreview from '@/components/LivePreview';
import ResultsPanel from '@/components/ResultsPanel';
import { useSSE } from '@/hooks/useSSE';
import { captureEmail, submitExtraction, getIntelDownloadUrl } from '@/lib/api';

type Phase = 'input' | 'submit' | 'processing' | 'results';

const PHASE_ORDER: Phase[] = ['input', 'submit', 'processing', 'results'];

function phaseIndex(p: Phase): number {
  return PHASE_ORDER.indexOf(p);
}

export default function CompanyIntelPage() {
  const [phase, setPhase] = useState<Phase>('input');
  const [direction, setDirection] = useState<'forward' | 'back'>('forward');

  // Input
  const [inputText, setInputText] = useState('');
  const lineStats = useMemo(() => computeLineStats(inputText), [inputText]);

  // Extraction options
  const [industryDescription, setIndustryDescription] = useState(true);
  const [targetMarket, setTargetMarket] = useState(true);
  const [companyPeople, setCompanyPeople] = useState(true);
  const [homepageRawText, setHomepageRawText] = useState(false);

  // API keys
  const [quickenrichApiKey, setQuickenrichApiKey] = useState('');
  const [serperApiKey, setSerperApiKey] = useState('');

  // Job state — restore from localStorage
  const [jobId, setJobId] = useState<string | null>(() => {
    if (typeof window === "undefined") return null;
    return localStorage.getItem("qe_intel_job_id");
  });
  const [token, setToken] = useState<string | null>(() => {
    if (typeof window === "undefined") return null;
    return localStorage.getItem("qe_intel_token");
  });

  // Submit state
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');

  // Persist job session
  useEffect(() => {
    if (jobId && token) {
      localStorage.setItem("qe_intel_job_id", jobId);
      localStorage.setItem("qe_intel_token", token);
    }
  }, [jobId, token]);

  // Resume saved job on mount
  useEffect(() => {
    if (jobId && token && phase === "input") {
      setPhase("processing");
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
    localStorage.removeItem("qe_intel_job_id");
    localStorage.removeItem("qe_intel_token");
    setJobId(null);
    setToken(null);
  }

  // Validation
  const canSubmit = lineStats.total > 0 &&
    (industryDescription || targetMarket || companyPeople || homepageRawText) &&
    (!companyPeople || quickenrichApiKey.trim()) &&
    (lineStats.names === 0 || serperApiKey.trim());

  async function handleEmailSubmit(email: string) {
    setIsSubmitting(true);
    setSubmitError('');

    try {
      const capture = await captureEmail(email, 'company-intel', 'company-intel-page');

      const lines = inputText.split('\n').filter((l) => l.trim());

      const result = await submitExtraction(
        {
          lines,
          options: {
            industry_description: industryDescription,
            target_market: targetMarket,
            company_people: companyPeople,
            homepage_raw_text: homepageRawText,
          },
          serper_api_key: serperApiKey,
          quickenrich_api_key: quickenrichApiKey,
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

  return (
    <main className="min-h-screen bg-gradient-to-b from-gray-50 to-white py-8 px-4">
      <div className="max-w-5xl mx-auto space-y-6">

        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center">
              <Search className="w-5 h-5 text-primary" />
            </div>
            <h1 className="text-xl font-bold text-text-primary">
              Company/People Intel by URL
            </h1>
          </div>
          <div className="flex items-center gap-2 text-sm text-text-secondary">
            <Building2 className="w-4 h-4" />
            <span>Company Intelligence</span>
          </div>
        </div>

        {/* Content */}
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={phase}
            initial={{ opacity: 0, x: entering ? 40 : -40 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: entering ? -40 : 40 }}
            transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
          >
            {/* ---- PHASE: input ---- */}
            {phase === 'input' && (
              <div className="bg-white rounded-2xl border border-border shadow-sm p-6 sm:p-8 space-y-6">
                <div>
                  <h2 className="text-2xl font-bold text-text-primary">Extract Deep Insights</h2>
                  <p className="text-text-secondary mt-1">
                    Paste a list of URLs or company names (one per line). We&apos;ll automatically determine
                    if we need to search for the website or scrape it directly to gather the intelligence you need.
                  </p>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
                  {/* Textarea — 3 cols */}
                  <div className="lg:col-span-3">
                    <IntelInputPanel
                      value={inputText}
                      onChange={setInputText}
                      lineStats={lineStats}
                    />
                  </div>

                  {/* Settings — 2 cols */}
                  <div className="lg:col-span-2">
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
                      serperApiKey={serperApiKey}
                      onSerperApiKeyChange={setSerperApiKey}
                      showSerperKey={lineStats.names > 0}
                    />
                  </div>
                </div>

                <div className="flex justify-end">
                  <Button
                    onClick={() => navigate('submit')}
                    disabled={!canSubmit}
                    className="px-8 py-2.5 gap-2"
                  >
                    <Search className="w-4 h-4" />
                    Run Extraction
                  </Button>
                </div>
              </div>
            )}

            {/* ---- PHASE: submit ---- */}
            {phase === 'submit' && (
              <div className="bg-white rounded-2xl border border-border shadow-sm p-6 sm:p-8 max-w-lg mx-auto space-y-6">
                <div>
                  <h2 className="text-lg font-semibold text-text-primary">Almost there!</h2>
                  <p className="text-sm text-text-secondary mt-0.5">
                    Enter your email to start processing{' '}
                    <span className="font-medium text-text-primary">{lineStats.total} companies</span>.
                    We&apos;ll email you when done.
                  </p>
                </div>

                <EmailGate onSubmit={handleEmailSubmit} isLoading={isSubmitting} />

                {submitError && (
                  <p className="text-sm text-red-600" role="alert">{submitError}</p>
                )}

                <button
                  type="button"
                  onClick={() => navigate('input')}
                  className="text-sm text-text-secondary hover:text-text-primary transition-colors flex items-center gap-1"
                >
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
                  </svg>
                  Back to configuration
                </button>
              </div>
            )}

            {/* ---- PHASE: processing ---- */}
            {phase === 'processing' && progress && jobId && token && (
              <div className="bg-white rounded-2xl border border-border shadow-sm p-6 sm:p-8 space-y-8">
                <div className="text-center space-y-1">
                  <h2 className="text-xl font-semibold text-text-primary">
                    Extracting company intelligence…
                  </h2>
                  <p className="text-sm text-text-secondary">
                    This may take a few minutes. You can keep this tab open or close it — we&apos;ll email you.
                  </p>
                </div>

                <ProgressTracker
                  status={progress.status}
                  currentPhase={progress.current_phase}
                  phaseProgress={progress.phase_progress}
                  processedRows={progress.processed_rows}
                  totalRows={progress.total_rows}
                  foundCount={progress.found_count}
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
              <div className="bg-white rounded-2xl border border-border shadow-sm p-6 sm:p-8">
                <div className="flex flex-col items-center gap-4 py-12 text-text-secondary">
                  <svg className="w-6 h-6 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  <p className="text-sm">Connecting…</p>
                </div>
              </div>
            )}

            {/* ---- PHASE: results ---- */}
            {phase === 'results' && jobId && token && (
              <div className="bg-white rounded-2xl border border-border shadow-sm p-6 sm:p-8 space-y-6">
                <ResultsPanel
                  jobId={jobId}
                  token={token}
                  totalRows={progress?.total_rows ?? 0}
                  foundCount={progress?.found_count ?? 0}
                  enrichedCount={companyPeople ? (progress?.found_count ?? 0) : 0}
                  downloadUrlOverride={getIntelDownloadUrl(jobId, token)}
                />
                <div className="text-center">
                  <Button
                    variant="ghost"
                    onClick={() => {
                      clearSession();
                      setPhase("input");
                      setInputText("");
                    }}
                  >
                    Start a new extraction
                  </Button>
                </div>
              </div>
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </main>
  );
}
```

- [ ] **Step 2: Add downloadUrlOverride prop to ResultsPanel**

The ResultsPanel component needs a `downloadUrlOverride` prop so the intel page can use `/intel/download/` instead of the default `/download/` URL. Read `frontend/src/components/ResultsPanel.tsx` to understand its props, then add the optional `downloadUrlOverride?: string` prop. In the download button's onClick or href, use `downloadUrlOverride ?? getDownloadUrl(jobId, token)`.

This is a small change — add the prop to the interface and use it in the download logic. The exact edit depends on how ResultsPanel currently constructs the download URL.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/tools/company-intel/page.tsx frontend/src/components/ResultsPanel.tsx
git commit -m "feat(intel): add company intel tool page with full 4-phase UI flow"
```

---

## Task 11: Integration Testing + Fixes

- [ ] **Step 1: Install backend dependencies**

```bash
cd backend && pip install -r requirements.txt
```

- [ ] **Step 2: Install frontend dependencies and verify build compiles**

```bash
cd frontend && npm install
```

- [ ] **Step 3: Verify backend starts without import errors**

```bash
cd backend && python -c "from app.main import app; print('OK')"
```

Fix any import errors that surface.

- [ ] **Step 4: Verify frontend has no TypeScript errors**

Check for type errors in the new components. Fix any issues.

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat(intel): complete Product 3 - Company/People Intel by URL"
```

---

## Summary

| Task | Description | New Files | Modified Files |
|------|-------------|-----------|----------------|
| 1 | DB schema + config + model | 2 SQL migrations | config.py, models.py |
| 2 | Refactor serper/enrichment for user keys | — | serper.py, enrichment.py |
| 3 | Scraper service (Scrape.do) | scraper.py | requirements.txt |
| 4 | Intel extractor service (LLM) | intel_extractor.py | — |
| 5 | Intel pipeline worker | intel_pipeline.py | — |
| 6 | Intel router + main.py wiring | intel.py | main.py |
| 7 | Frontend API client + registry | — | api.ts, tool-registry.ts, page.tsx |
| 8 | IntelInputPanel component | IntelInputPanel.tsx | — |
| 9 | ExtractionSettings component | ExtractionSettings.tsx | — |
| 10 | Main tool page | company-intel/page.tsx | ResultsPanel.tsx |
| 11 | Integration testing + fixes | — | various |
