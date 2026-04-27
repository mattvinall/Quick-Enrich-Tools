# G2 Category → Company Intel

Select one or more G2 software categories. The pipeline scrapes G2 to
discover the companies listed, then runs each company through the
company-intel pipeline (crawl + LLM extraction).

## Pipeline phases

6 phases: **Discover (G2 scrape) → Resolve → Crawl → Extract → Enrich → Deliver.**

## User flow

1. Browse the static category registry (~175 categories), pick one or more.
2. Set per-category cap (default 25 products).
3. Confirm email; submit.
4. Watch live progress as G2 is scraped, then each company is enriched.
5. Download CSV.

## Backend

- **Route:** `/tools/g2-intel`
- **Router:** `backend/app/routers/g2.py`
- **Pipeline worker:** `backend/app/workers/g2_pipeline.py`
- **Discovery phase (Phase 0):** `backend/app/services/g2_scraper.py` (categories registry: `backend/app/services/g2_categories.py`)
- **Services touched:** Serper (fallback discovery + Resolve), Scrape.do (G2 scrape + Crawl), LLM (Extract)

## Notable design decisions

- **G2 actively blocks scraping.** Scrape.do is the difference between full coverage (~80+ products per category) and Google-search fallback (~10 per category). The pipeline degrades gracefully without Scrape.do — users will see fewer rows.
- Discovery results are cached for 3 days (`g2_cache_ttl_days` in config) to avoid re-burning Scrape.do credits on the same category.
- Hard ceilings: `g2_max_pages_per_category=500` and `g2_max_total_companies=50000` are runaway-protection caps.

## Key files

- Frontend page: `frontend/src/app/tools/g2-intel/page.tsx`
- Backend router: `backend/app/routers/g2.py`
- Pipeline worker: `backend/app/workers/g2_pipeline.py`
- Discovery: `backend/app/services/g2_scraper.py` + `backend/app/services/g2_categories.py`
