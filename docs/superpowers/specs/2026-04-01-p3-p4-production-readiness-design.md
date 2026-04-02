# P3/P4 Production Readiness Design

## Context

Product 3 (Company/People Intel by URL, codebase: `company-intel`) and Product 4 (G2 Category to Company Intel, codebase: `g2-intel`) need to be production-ready before testing. P4 discovers companies from G2 categories and feeds them into P3's intel pipeline.

This spec addresses all gaps identified between the product specs and current implementation.

## Scope

10 gaps across both products. The most impactful change is replacing Serper-only G2 discovery with scrape.do-based G2 category page scraping, with Serper as fallback.

---

## Gap 1: G2 Discovery via scrape.do (Critical)

### Problem
The UI offers 50/100/250/500 companies per category, but Serper `site:g2.com` returns ~100-150 max. Users selecting "500" get ~120.

### Design

**Primary: Scrape G2 category listing pages with scrape.do**

G2 category pages follow the pattern:
```
https://www.g2.com/categories/{slug}
https://www.g2.com/categories/{slug}?page=2
```

Each page lists ~25 products with: name, website URL, rating, review count.

**Implementation in `g2_scraper.py`:**

Reuse the existing `scrape_page()` from `scraper.py` (already handles scrape.do API key, retry logic, URL encoding) rather than building a separate scrape.do integration.

New function `_parse_g2_category_html(html)`:
- Parse product cards from G2 category page HTML
- Extract per product: `name`, `website`, `rating`, `review_count`, `g2_url`
- Handle partial parsing failures gracefully: if 20/25 cards parse and 5 fail, keep the 20 and log warnings. Only fall back to Serper on page-level failures (HTTP error, DataDome block).
- Handle G2 redirect URLs: extract actual destination URL, not `g2.com/products/xyz/visit_website` links.
- Return list of product dicts and detected total page count

New function `discover_g2_category_via_scrape(client, category_slug, category_name, max_products, semaphore)`:
- Page 1 first, parse products and detect total page count
- Stop conditions: (a) `ceil(max_products / 25)` pages reached, (b) page returns fewer than 25 products (small category), (c) no more pages detected
- Add 1-2 second delay between page requests within a category to avoid DataDome rate limiting
- Deduplicate by product slug
- Cache results with key prefix `g2_cat_scrape` (distinct from Serper cache key `g2_cat`) to avoid cache collisions between the two discovery methods
- On page-level scrape.do failure (DataDome block, HTTP 403/500): fall back to current Serper method for that category. Transient errors on individual pages (timeout on page 5 of 8) should retry once, then skip that page rather than falling back entirely.

Update `batch_scrape_g2_categories()`:
- Try scrape.do first for each category
- Track which categories failed and retry those via Serper
- Merge and deduplicate across all categories and sources. When the same product appears from both scrape.do and Serper, prefer the scrape.do result (richer data: rating, review_count, website populated)
- Accept optional progress callback (see Gap 5) — called after each category completes

**Fallback: Current Serper method (unchanged)**

The existing `discover_g2_category()` function stays as-is. It becomes the fallback when scrape.do can't get through DataDome.

**Rate limiting:** The existing `g2_scrape_concurrency` semaphore (default 5) controls how many categories run in parallel. Within a single category, page requests are sequential with a 1-2 second delay to avoid triggering DataDome.

### Product dict structure
Each product dict from scrape.do:
```python
{
    "name": "HeyReach",
    "website": "heyreach.io",           # NEW — extracted from G2 listing
    "g2_url": "https://www.g2.com/products/heyreach",
    "g2_category": "sales-intelligence",
    "rating": 4.5,                       # NEW — populated from G2
    "review_count": 1250,                # NEW — populated from G2
}
```

From Serper fallback (unchanged):
```python
{
    "name": "HeyReach",
    "website": None,                     # Not available from Serper
    "g2_url": "https://www.g2.com/products/heyreach",
    "g2_category": "sales-intelligence",
    "rating": None,                      # Not available from Serper
    "review_count": None,                # Not available from Serper
}
```

### Files Changed
- `backend/app/services/g2_scraper.py` — add scrape.do category scraping, keep Serper as fallback

---

## Gap 2: G2 Rating and Review Count (Critical)

### Problem
CSV has `g2_rating` and `g2_review_count` columns but they're always null.

### Design

When scraping G2 category pages (Gap 1), extract rating and review count from the product listing HTML. Each product card on G2 contains a star rating and review count.

The scrape.do parsing in Gap 1 already extracts these. They flow into:
- `g2_scraper.py` product dict: `{"rating": 4.5, "review_count": 1250}`
- `g2_pipeline.py` JobResult.input_data: `{"g2_rating": 4.5, "g2_review_count": 1250}`
- `g2.py` CSV download: already reads from `input_data`

For the Serper fallback path, rating/review_count remain null (Serper doesn't provide them). This is acceptable — partial data is better than no data.

### Files Changed
- `backend/app/services/g2_scraper.py` — parsing logic (part of Gap 1)

---

## Gap 3: Extract Company Website from G2 (Critical)

### Problem
G2 product listings show the company's website. Currently the pipeline discovers the company name, then does a second Serper search just to find their website. Wasteful and less accurate.

### Design

When scraping G2 category pages, extract the website URL from each product card. The `website` field in the product dict stores the domain (e.g., `"heyreach.io"`).

In `g2_pipeline.py`, when building JobResult rows:

If `website` is present in the product dict:
- Set `input_data["input"]` to the **website URL** (not the company name)
- Set `input_data["input_type"]` to `"url"`
- The resolve phase (`_phase_resolve_worker` line 108-111) reads `input_data["input"]` and passes it to `_extract_domain_from_url()` — this extracts the domain directly, skipping Serper entirely
- Store the company name in a separate field `input_data["company_name"]` for display purposes

If `website` is null (Serper fallback or not found on G2):
- Keep `input_data["input"]` as the company name
- Keep `input_data["input_type"]` as `"name"` — resolve phase does a Serper search

This saves one Serper API call per company where we get the website from G2.

### Files Changed
- `backend/app/services/g2_scraper.py` — extract website from product cards
- `backend/app/workers/g2_pipeline.py` — set `input_type` and `input` based on whether website was found

---

## Gap 4: G2 Pipeline Missing serper_api_key Pass-through (Critical)

### Problem
`G2ExtractRequest` doesn't include `serper_api_key`. Inconsistent with P3.

### Design

Add `serper_api_key: str = ""` to `G2ExtractRequest` model in `g2.py`. Pass it into `job_config` dict. The intel pipeline reads `config.get("serper_api_key")` at `intel_pipeline.py` line 121 and passes it to `batch_search()`. Since `run_intel_pipeline` reads config from `job.config` (which was set from `job_config`), the key flows through automatically.

Frontend changes:
- Add `serper_api_key` field to `G2ExtractRequest` interface in `api.ts`
- Pass `serperApiKey` state value in the `submitG2Extraction` call in `g2-intel/page.tsx`

### Files Changed
- `backend/app/routers/g2.py` — add field to `G2ExtractRequest` model and `job_config` dict
- `frontend/src/lib/api.ts` — add `serper_api_key` to `G2ExtractRequest` interface
- `frontend/src/app/tools/g2-intel/page.tsx` — add state, pass in submit call

---

## Gap 5: G2 Phase 0 Progress Feedback (Moderate)

### Problem
During G2 discovery (Phase 0), users see "g2_scraping" with no granular progress. For 10+ categories this could take a minute.

### Design

Update `batch_scrape_g2_categories` to accept an optional `on_progress` callback: `Callable[[int, int], Awaitable[None]]` called with `(done, total)` after each category completes. The G2 pipeline passes a callback that calls `update_job_progress(db, job_id, "g2_scrape", done, total)`.

This is implemented as part of Gap 1's `batch_scrape_g2_categories` refactor to avoid touching the function twice.

### Files Changed
- `backend/app/services/g2_scraper.py` — add progress callback parameter (part of Gap 1 refactor)
- `backend/app/workers/g2_pipeline.py` — pass progress updater callback

---

## Gap 6: Frontend Error Handling on Category Fetch (Moderate)

### Problem
G2CategorySelector silently swallows fetch errors. Users see "No categories match" with no indication the API failed.

### Design

Add an `error` state to the component. When the fetch fails, show: "Failed to load categories." with a "Retry" button. On retry, clear error and re-fetch.

### Files Changed
- `frontend/src/components/G2CategorySelector.tsx` — add error state, retry button

---

## Gap 7: G2 Frontend Missing Serper API Key Field (Moderate)

### Problem
G2 page doesn't pass Serper API key props to ExtractionSettings. G2 always discovers company names, so the field should always show.

### Design

Add Serper API key state to the G2 page. Pass `hasCompanyNames={true}`, `serperApiKey`, and `onSerperApiKeyChange` to `ExtractionSettings`. Pass the key through to `submitG2Extraction`.

### Files Changed
- `frontend/src/app/tools/g2-intel/page.tsx` — add state, pass props to ExtractionSettings and submit call

---

## Gap 8: G2 Pipeline Phase Name Mapping (Moderate)

### Problem
Frontend defines `['Discover', 'Resolve', 'Crawl', 'Extract', 'Enrich', 'Deliver']` but backend uses `g2_scrape` for the discovery phase.

### Design

Verified from code review: `ProgressTracker` has a `PHASE_ALIASES` mapping that normalizes `g2_scrape` to `discover`, and `findPhaseIndex` uses this to find index 0 in the phase list. This works correctly. Quick verification task — confirm visually during testing that the stepper highlights the correct phase.

### Files Changed
- None expected — verify during testing

---

## Gap 9: Hardcoded estimated_products (Minor)

### Problem
Category selector shows hardcoded estimates like "~250" that may not match reality.

### Design

Append "(est.)" to the count display to set expectations. Low priority.

### Files Changed
- `frontend/src/components/G2CategorySelector.tsx` — append "(est.)" to count display

---

## Gap 10: G2 URL Not Shown in Results (Minor)

### Problem
`g2_url` is stored in `input_data` but not visible in LivePreview or ResultsPanel.

### Design

Add `g2_url` as a clickable column in the G2 results table and include it in the CSV download.

### Files Changed
- `frontend/src/components/ResultsPanel.tsx` or `LivePreview.tsx` — add G2 URL column for g2-intel tool
- `backend/app/routers/g2.py` — add `g2_url` to CSV base columns

---

## Implementation Order

1. **Gap 1 + 2 + 3 + 5** (G2 scrape.do discovery with ratings, reviews, website, progress callback) — all in `g2_scraper.py` + `g2_pipeline.py`. Grouped because they all modify the same functions.
2. **Gap 4 + 7** (serper_api_key pass-through for G2 frontend + backend)
3. **Gap 6** (Category fetch error handling)
4. **Gap 8** (Phase name mapping verification — quick visual check)
5. **Gap 10** (G2 URL in results)
6. **Gap 9** (estimated products label)

## Risks

- **DataDome blocking scrape.do on G2:** Mitigated by Serper fallback per-category. If scrape.do with residential proxies + JS rendering can't bypass DataDome, we gracefully degrade to Serper-only discovery (~150 per category). The system works either way.
- **G2 HTML structure changes:** Product card parsing could break if G2 redesigns their category pages. Mitigation: partial parsing failures are handled gracefully (keep what parsed, skip what didn't), and page-level failures trigger Serper fallback.
- **scrape.do credit usage:** G2 category pages with `render=true` use 1 credit each. For 10 categories x 20 pages = 200 credits. Well within free tier (1,000/mo) for testing.
- **Rate limiting within G2:** Mitigated by 1-2 second delay between page requests within a category and `g2_scrape_concurrency` semaphore (default 5) across categories.
