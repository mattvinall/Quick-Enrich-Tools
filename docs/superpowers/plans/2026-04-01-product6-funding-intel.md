# Product 6: Funded Companies Today — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Add a "Funded Companies Today" tool that discovers recently funded companies via Serper news search + Gemini LLM extraction, then feeds them through the existing intel pipeline.

**Architecture:** New funding discovery service (Serper /news + Gemini extraction) → new funding_pipeline.py (Phase 0 discovery + delegate to intel_pipeline) → new funding router → new frontend page with discovery panel. Same Phase 0 + delegation pattern as Products 4 and 5.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, Serper API `/news`, Gemini 2.5 Flash, httpx (all existing)

**Spec:** `docs/superpowers/specs/2026-04-01-product6-funding-intel-design.md`

---

## File Map

### New Files
| File | Responsibility |
|------|---------------|
| `backend/app/services/funding_discovery.py` | Serper /news queries + Gemini LLM extraction + caching |
| `backend/app/workers/funding_pipeline.py` | Phase 0 (create JobResults from selected companies) + delegate to intel_pipeline |
| `backend/app/routers/funding.py` | API routes: GET `/funding/discover`, POST `/funding/extract`, GET `/funding/download/{job_id}` |
| `frontend/src/app/tools/funding-intel/page.tsx` | Main page (4-step wizard) |
| `frontend/src/components/FundingDiscoveryPanel.tsx` | Funding company table with round-type filters + selection |

### Modified Files
| File | Change |
|------|--------|
| `backend/app/main.py` | Import + register funding router |
| `backend/app/workers/intel_pipeline.py` | Add `"funding-intel": "funding"` to dl_slug_map |
| `frontend/src/lib/api.ts` | Add funding API client functions |
| `frontend/src/lib/tool-registry.ts` | Add funding-intel tool config |
| `frontend/src/app/page.tsx` | Add funding-intel icon |
| `frontend/src/components/ProgressTracker.tsx` | Add `funding_discovering` phase alias |

---

## Task 1: Create Funding Discovery Service

**Files:** Create `backend/app/services/funding_discovery.py`

This service fetches funding news via Serper `/news`, extracts structured data via Gemini, and returns deduplicated funding entries. Cached for 1 hour.

Key functions:
- `discover_funded_companies(hours: int = 24) -> list[dict]` — main entry point
- `_fetch_funding_news(hours: int) -> list[dict]` — runs 3 Serper /news queries in parallel
- `_extract_funding_data(articles: list[dict]) -> list[dict]` — batches to Gemini for structured extraction
- `_deduplicate_companies(entries: list[dict]) -> list[dict]` — dedup by company name

Commit: `feat(funding): add funding discovery service with Serper news + Gemini extraction`

## Task 2: Create Funding Pipeline Worker + Wire Up

**Files:**
- Create `backend/app/workers/funding_pipeline.py`
- Modify `backend/app/workers/intel_pipeline.py` (add to dl_slug_map)
- Modify `backend/app/main.py` (register router + worker)

Pipeline takes selected companies from the discovery list, creates JobResult rows with funding metadata in input_data, then delegates to intel_pipeline.

Commit: `feat(funding): add funding pipeline worker and register in main app`

## Task 3: Create Funding API Router

**Files:** Create `backend/app/routers/funding.py`

Three endpoints:
- `GET /funding/discover` — returns cached list of today's funded companies (no auth)
- `POST /funding/extract` — creates job from selected companies (auth required)
- `GET /funding/download/{job_id}` — streams CSV with funding metadata + intel columns

Commit: `feat(funding): add funding router with discover, extract, and download endpoints`

## Task 4: Add Frontend API Client + Tool Registry

**Files:**
- Modify `frontend/src/lib/api.ts` — add `discoverFunding()`, `submitFundingExtraction()`, `getFundingDownloadUrl()`
- Modify `frontend/src/lib/tool-registry.ts` — add funding-intel entry
- Modify `frontend/src/app/page.tsx` — add DollarSign + Users icon
- Modify `frontend/src/components/ProgressTracker.tsx` — add `funding_discovering: 'discover'` alias

Commit: `feat(funding): add frontend API client and register tool`

## Task 5: Create FundingDiscoveryPanel Component

**Files:** Create `frontend/src/components/FundingDiscoveryPanel.tsx`

Table component showing discovered funding companies with:
- Checkbox selection per row
- Filter pills: All, Seed, Series A, Series B, Series C+, Growth, Unknown
- Select All / Deselect All buttons
- 24h / 48h toggle
- Refresh button
- Loading/error states
- Columns: checkbox, Company Name, Amount, Round, Lead Investor, Description

Commit: `feat(funding): create FundingDiscoveryPanel component`

## Task 6: Create Funding Intel Page

**Files:** Create `frontend/src/app/tools/funding-intel/page.tsx`

4-step wizard following G2/Maps pattern:
1. `discover` — FundingDiscoveryPanel (auto-loads on mount)
2. `configure` — ExtractionSettings (reused)
3. `submit` — EmailGate (reused)
4. `processing` / `results` — ProgressTracker + LivePreview + ResultsPanel (reused)

Commit: `feat(funding): create funding-intel page with 4-step wizard`

## Task 7: Smoke Test & Code Review

- Verify backend imports: `python -c "from app.main import app"`
- Verify frontend compilation: `npx tsc --noEmit`
- Fix any issues found

Commit: `fix(funding): resolve any import/type errors`
