# Google Maps → Company Intel

Search Google Maps by category and location to discover businesses, then
run each business through the company-intel pipeline.

## Pipeline phases

6 phases: **Discover (Serper /maps) → Resolve → Crawl → Extract → Enrich → Deliver.**

## User flow

1. Pick a search mode:
   - **Interactive:** type a category + location (e.g. "dentists in Austin TX").
   - **CSV upload:** rows of category + location for batch discovery.
2. Confirm email; submit.
3. Watch progress as Maps is queried, then each business is enriched.
4. Download CSV.

## Backend

- **Route:** `/tools/maps-intel`
- **Router:** `backend/app/routers/maps.py`
- **Pipeline worker:** `backend/app/workers/maps_pipeline.py`
- **Discovery phase (Phase 0):** Serper `/maps` endpoint — no new dependency, same Serper key as the rest of the suite.
- **Services touched:** Serper (Discover + Resolve), Scrape.do (Crawl), LLM (Extract)

## Notable design decisions

- **No new external dep for discovery.** Reusing the existing Serper key (which already does web search elsewhere) was a deliberate choice over Google Places API.
- **Tile-grid expansion.** A single `/maps` call covers a small area; for thicker coverage the pipeline fans out into a lat/lng grid around the seed centroid (`maps_expansion_max_tiles=6`, `maps_expansion_max_radius_km=50` in config).
- **Pagination cap.** Page 2+ is empirically empty on Serper `/maps`, so `maps_max_pages_per_search=5` is a generous safety cap.

## Key files

- Frontend page: `frontend/src/app/tools/maps-intel/page.tsx`
- Backend router: `backend/app/routers/maps.py`
- Pipeline worker: `backend/app/workers/maps_pipeline.py`
- Discovery: Serper `/maps` calls live in `backend/app/services/serper.py`
