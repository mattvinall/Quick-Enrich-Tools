# Funded Companies Today

Discovers companies that received funding in the last 24-48 hours via Serper
news + Gemini extraction, lets users browse and select, then runs the
selected companies through the company-intel pipeline.

## Pipeline phases

6 visible phases: **Discover → Resolve → Crawl → Extract → Enrich → Deliver.**

## User flow

1. Pick a window: 24h or 48h.
2. Browse the discovered list (company name, funding amount, round, lead investor).
3. Filter / select the companies you want enriched.
4. Confirm email; submit.
5. Watch progress; download CSV.

## Backend

- **Route:** `/tools/funding-intel`
- **Router:** `backend/app/routers/funding.py`
- **Pipeline worker:** `backend/app/workers/funding_pipeline.py`
- **Discovery phase (Phase 0):** `backend/app/services/funding_discovery.py` — runs 3 parallel Serper `/news` queries, batches headlines to Gemini for structured extraction (company_name, funding_amount, funding_round, lead_investor), deduplicates.
- **Services touched:** Serper (Discover + Resolve), Gemini (Discover extraction), Scrape.do (Crawl), LLM (Extract)

## Notable design decisions

- **`/discover` endpoint restricted to `hours=24|48`.** Both values are hot-cached for 1 hour. Wider windows would invite cache abuse and ramp Serper costs unpredictably.
- **Discovery cache is per-window, 1h TTL.** Re-queries within the same hour are free.
- **CSV columns** include funding metadata (`company_name`, `funding_amount`, `funding_round`, `lead_investor`, `source_url`, `source_name`) **plus** all the standard intel columns from the company-intel pipeline.

## Key files

- Frontend page: `frontend/src/app/tools/funding-intel/page.tsx`
- Backend router: `backend/app/routers/funding.py`
- Pipeline worker: `backend/app/workers/funding_pipeline.py`
- Discovery: `backend/app/services/funding_discovery.py`
