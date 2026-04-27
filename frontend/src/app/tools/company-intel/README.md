# Company / People Intel by URL

Paste URLs or company names; the pipeline crawls each website (via Scrape.do
to bypass anti-bot), extracts structured business intelligence with an LLM
(industry, niche, description, target market, case studies, contacts), and
optionally enriches named contacts via QuickEnrich.

## Pipeline phases

5-phase: **Resolve → Crawl → Extract → Enrich → Deliver.** No Phase 0
discovery — input is provided directly by the user.

## User flow

1. Paste URLs (one per line) or company names.
2. Provide your own Serper API key (used for name → URL resolution).
3. Provide your own QuickEnrich key if you want named contacts.
4. Confirm email; submit.
5. Live SSE progress; download CSV when done.

## Backend

- **Route:** `/tools/company-intel`
- **Router:** `backend/app/routers/intel.py`
- **Pipeline worker:** `backend/app/workers/intel_pipeline.py`
- **Discovery phase (Phase 0):** none — input is URLs or company names.
- **Services touched:** Serper (Resolve), Scrape.do (Crawl), LLM Gemini/OpenAI (Extract), QuickEnrich (Enrich, optional)

## Notable design decisions

- **User provides their own Serper and QuickEnrich keys.** This is the only tool with that pattern. Backend pays for Scrape.do and LLM tokens; those are fixed-cost per row. Serper and QuickEnrich are per-request and would be expensive if backend covered them at scale.
- LLM extraction is batched (`llm_batch_size` in config) to amortize prompt overhead.
- Force-UTF-8 on QuickEnrich responses (see commit `40d8b52`) — don't strip that handling.

## Key files

- Frontend page: `frontend/src/app/tools/company-intel/page.tsx`
- Backend router: `backend/app/routers/intel.py`
- Pipeline worker: `backend/app/workers/intel_pipeline.py`
- Crawling: `backend/app/services/scraper.py`
- Extraction: `backend/app/services/intel_extractor.py` + `backend/app/services/llm/`
- Contact enrichment: `backend/app/services/enrichment.py`
