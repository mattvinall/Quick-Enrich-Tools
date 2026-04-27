# People Intel by Name

Upload person names + company names. The pipeline finds matching LinkedIn
profiles via Serper search and (optionally) enriches via QuickEnrich.
Single-contact CSV output.

## User flow

1. Upload a CSV with `name` and `company_name` columns (or paste rows).
2. Map the columns.
3. Confirm email; submit.
4. Watch progress as each name is resolved.
5. Download CSV with one row per person.

## Backend

- **Route:** `/tools/people-intel`
- **Router:** `backend/app/routers/people.py`
- **Pipeline worker:** `backend/app/workers/people_pipeline.py`
- **Discovery phase (Phase 0):** `backend/app/services/linkedin_search.py`
- **Services touched:** Serper (LinkedIn search), QuickEnrich (contact enrichment, optional)

## Notable design decisions

- **Lookup by name, not scraping.** This tool deliberately does not crawl LinkedIn — it uses Serper's Google index to find profile URLs. Faster, no anti-bot fight, no Scrape.do dependency.
- **Single contact per row.** Unlike `company-intel` which can return multiple contacts per company, this tool produces exactly one row per input person. (See commit `a7565d8`.)

## Key files

- Frontend page: `frontend/src/app/tools/people-intel/page.tsx`
- Backend router: `backend/app/routers/people.py`
- Pipeline worker: `backend/app/workers/people_pipeline.py`
- Discovery: `backend/app/services/linkedin_search.py`
