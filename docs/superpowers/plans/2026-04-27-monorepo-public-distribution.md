# Public Distribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the QuickEnrich monorepo as a public, agent-friendly, MIT-licensed open-source repo that any developer can clone and run locally with their own API keys.

**Architecture:** Documentation + light cleanup, no code architecture changes. AGENTS.md is the cross-agent source of truth; CLAUDE.md is a one-line stub. README is local-first; hosted-mode is a separate `docs/hosting.md`. Provider swaps are documented in tiers in `docs/swapping-providers.md`. Pre-flight gate: rotate the 4 leaked keys (Serper/Gemini/OpenAI/QuickEnrich), then `git filter-repo` scrubs them from history before the public flip.

**Tech Stack:** Existing — Python 3.11 / FastAPI / ARQ / SQLAlchemy (async) / Next.js 14 / Tailwind / Supabase / Railway / Vercel. New tooling: `git filter-repo` (one-time scrub), `docker-compose` (local Postgres + Redis).

**Spec:** `docs/superpowers/specs/2026-04-27-monorepo-public-distribution-design.md`

---

## File-Structure Map

**New files:**
- `LICENSE` — MIT
- `AGENTS.md` — cross-agent guidance (root)
- `CLAUDE.md` — one-line redirect to AGENTS.md
- `README.md` — replace existing if any (local-first framing)
- `docker-compose.yml` — local Postgres + Redis
- `docs/hosting.md` — hosted-deployment playbook
- `docs/swapping-providers.md` — tiered provider-swap recipes
- `frontend/src/app/tools/company-location-finder/README.md`
- `frontend/src/app/tools/company-intel/README.md`
- `frontend/src/app/tools/g2-intel/README.md`
- `frontend/src/app/tools/maps-intel/README.md`
- `frontend/src/app/tools/funding-intel/README.md`
- `frontend/src/app/tools/people-intel/README.md`

**Modified files:**
- `backend/.env.example` — annotate with comments + REQUIRED/OPTIONAL markers
- `frontend/.env.example` — create if missing, annotate
- `frontend/src/app/page.tsx` — add GitHub CTA section near bottom
- `frontend/src/components/` — possibly add a `<GithubBanner />` component used by the homepage

**Deleted:**
- `standalone/g2-intel/` (entire directory)

**Git history:** the blob containing leaked keys at commit `95a479b` is purged via `git filter-repo`.

---

## Pre-flight Gate (USER ACTION — blocks all later tasks)

Before any later task can execute, the user must:

1. Rotate Serper API key.
2. Rotate Gemini API key.
3. Rotate OpenAI API key (`REDACTED_OPENAI_KEY_FRAGMENT…`).
4. Rotate QuickEnrich API key.
5. Update Railway env vars + local `.env` with new values.
6. Smoke-test one tool end-to-end on staging/prod.
7. Confirm to the agent: "keys rotated, ready to scrub."

Tasks 1–11 below DO NOT depend on rotation. Tasks 12–17 (history scrub, push, public flip, smoke test) DO. The plan splits the work so doc-writing can happen in parallel with the user rotating keys.

---

## Task 1: Delete `standalone/g2-intel/`

**Files:**
- Delete: `standalone/g2-intel/` (entire directory: README.md, SOP.md, UPGRADE.md, requirements.txt, run.py, intel/*)

- [ ] **Step 1: Confirm directory contents one more time**

Run: `ls standalone/g2-intel`
Expected output:
```
README.md  SOP.md  UPGRADE.md  intel  requirements.txt  run.py
```

- [ ] **Step 2: Delete the directory**

Run: `rm -rf standalone/g2-intel && rmdir standalone 2>/dev/null || true`
(The second command removes the now-empty `standalone/` parent. If other entries exist later, the `|| true` keeps the step from failing.)

- [ ] **Step 3: Verify deletion**

Run: `ls standalone 2>/dev/null; echo "exit=$?"`
Expected: directory does not exist (`exit` is non-zero) OR is empty.

- [ ] **Step 4: Commit**

```bash
git add -A standalone/ 2>/dev/null
git rm -r --cached standalone 2>/dev/null || true
git commit -m "chore: remove standalone/g2-intel CLI artifact

Half-orphaned artifact from a different distribution bet (laptop CLI users).
The full monorepo is the new distribution path; per-tool CLIs aren't part
of the public-distribution plan. Git history preserves it if ever needed.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Add root `docker-compose.yml` for local Postgres + Redis

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1: Create the compose file**

Write `docker-compose.yml` (root) with this exact content:

```yaml
# Local-mode infrastructure for QuickEnrich.
# Brings up Postgres 16 + Redis 7 on the standard ports so the backend
# (uvicorn) and frontend (npm run dev) can run on the host.
#
# Usage:
#   docker compose up -d              # start in background
#   docker compose down               # stop
#   docker compose down -v            # stop and wipe volumes (fresh DB)
#
# Backend connects via DATABASE_URL=postgresql+asyncpg://quickenrich:quickenrich@localhost:5432/quickenrich
# Backend connects via REDIS_URL=redis://localhost:6379

services:
  postgres:
    image: postgres:16-alpine
    container_name: quickenrich-postgres
    environment:
      POSTGRES_USER: quickenrich
      POSTGRES_PASSWORD: quickenrich
      POSTGRES_DB: quickenrich
    ports:
      - "5432:5432"
    volumes:
      - quickenrich_pgdata:/var/lib/postgresql/data
      - ./database/schema.sql:/docker-entrypoint-initdb.d/01-schema.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U quickenrich -d quickenrich"]
      interval: 5s
      timeout: 3s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: quickenrich-redis
    ports:
      - "6379:6379"
    volumes:
      - quickenrich_redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

volumes:
  quickenrich_pgdata:
  quickenrich_redisdata:
```

- [ ] **Step 2: Verify the file is valid YAML by booting it**

Run: `docker compose config`
Expected: prints the resolved config with no errors. (Skip if Docker isn't installed locally — note in the writeup and rely on smoke-test step in Task 17.)

- [ ] **Step 3: Spin up and verify Postgres + Redis come online**

Run: `docker compose up -d && docker compose ps`
Expected: both services in state `running` and `healthy` after ~10 seconds. Then bring back down: `docker compose down`.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add docker-compose for local Postgres + Redis

Removes 'install Postgres and Redis on your machine' friction for
local-mode users. Schema auto-loads from database/schema.sql on first
boot.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Annotate `backend/.env.example`

**Files:**
- Modify: `backend/.env.example`

Current content (verified at plan time):
```
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/quickenrich
REDIS_URL=redis://localhost:6379
JWT_SECRET=change-me-in-production
SERPER_API_KEY=your-serper-api-key
GEMINI_API_KEY=your-gemini-api-key
OPENAI_API_KEY=your-openai-api-key
RESEND_API_KEY=your-resend-api-key
QUICKENRICH_API_KEY=your-quickenrich-api-key
SCRAPE_DO_API_KEY=your-scrape-do-api-key
LLM_PROVIDER=gemini
STORAGE_BUCKET=quickenrich-results
FRONTEND_URL=http://localhost:3000
```

- [ ] **Step 1: Replace `backend/.env.example` entirely with annotated version**

Write the full new content:

```bash
# QuickEnrich backend environment
#
# Copy this file to backend/.env and fill in real values.
# All vars below default to safe local-mode values where possible.
# Comment legend:
#   [REQUIRED]  — backend won't start or won't function without this
#   [OPTIONAL]  — only needed for the feature it powers
#   [HOSTED]    — only needed when deploying to a server (Railway/Fly/etc.)

# ---------- Datastores ----------

# [REQUIRED] Postgres connection. Default value works with the local
# docker-compose Postgres started by `docker compose up -d`.
DATABASE_URL=postgresql+asyncpg://quickenrich:quickenrich@localhost:5432/quickenrich

# [REQUIRED] Redis connection (used by ARQ job queue + cache). Default
# works with the local docker-compose Redis.
REDIS_URL=redis://localhost:6379

# ---------- Auth ----------

# [REQUIRED] Used to sign internal job tokens. ANY random 32+ char string
# is fine for local. Generate one with: openssl rand -hex 32
JWT_SECRET=change-me-in-production

# ---------- External services ----------

# [REQUIRED] Serper.dev — Google search. Get a key at https://serper.dev
# Used by every tool for company/website resolution.
SERPER_API_KEY=your-serper-api-key

# [REQUIRED] One LLM provider key. Set LLM_PROVIDER below to match.
# Get Gemini at https://ai.google.dev (free tier works)
# Get OpenAI at https://platform.openai.com
GEMINI_API_KEY=your-gemini-api-key
OPENAI_API_KEY=your-openai-api-key
LLM_PROVIDER=gemini

# [REQUIRED for full output] Scrape.do — bypasses anti-bot for site scraping.
# Without this, scraping falls back to plain HTTPS and many sites will fail.
# Get a key at https://scrape.do
SCRAPE_DO_API_KEY=your-scrape-do-api-key

# [OPTIONAL] QuickEnrich — named-contact enrichment (email/LinkedIn lookups).
# Only needed if you want contact rows in the output. Get a key at
# https://quickenrich.io
QUICKENRICH_API_KEY=your-quickenrich-api-key

# [OPTIONAL] Resend — email delivery for completed-job CSVs. Without this,
# users still get a download link but no email. Get a key at https://resend.com
RESEND_API_KEY=your-resend-api-key

# ---------- Storage ----------

# [HOSTED] S3-compatible bucket name for completed CSVs. Local mode writes
# to disk so this is unused.
STORAGE_BUCKET=quickenrich-results

# ---------- App ----------

# [REQUIRED] Where the Next.js frontend lives. Used in CORS + email links.
FRONTEND_URL=http://localhost:3000
```

- [ ] **Step 2: Verify backend still starts with the new defaults**

Run: `cd backend && python -c "from app.config import settings; print(settings.database_url)"`
Expected: `postgresql+asyncpg://quickenrich:quickenrich@localhost:5432/quickenrich` (or whatever the user's `.env` overrides to).

- [ ] **Step 3: Commit**

```bash
git add backend/.env.example
git commit -m "docs: annotate backend/.env.example for local-first onboarding

Adds REQUIRED/OPTIONAL/HOSTED legend, comments per var, and changes
DATABASE_URL default to match the new docker-compose Postgres.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Create `frontend/.env.example`

**Files:**
- Create: `frontend/.env.example`

The frontend currently has no `.env.example`. There's exactly one env var the app reads: `NEXT_PUBLIC_API_URL` (see `frontend/src/lib/tool-registry.ts:12`).

- [ ] **Step 1: Create the file**

Write `frontend/.env.example`:

```bash
# QuickEnrich frontend environment
#
# Copy to frontend/.env.local and fill in.

# [REQUIRED for local] Where the FastAPI backend is reachable from the
# browser. Defaults to local backend in src/lib/tool-registry.ts; override
# here if your backend lives elsewhere.
NEXT_PUBLIC_API_URL=http://localhost:8000
```

- [ ] **Step 2: Verify the var is honored**

Run: `cd frontend && grep -n 'NEXT_PUBLIC_API_URL' src/lib/tool-registry.ts`
Expected: returns line `12:const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";`

- [ ] **Step 3: Commit**

```bash
git add frontend/.env.example
git commit -m "docs: add frontend/.env.example

Documents NEXT_PUBLIC_API_URL — the only env the frontend reads.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Add `LICENSE` (MIT)

**Files:**
- Create: `LICENSE`

- [ ] **Step 1: Confirm copyright holder name with the user**

The spec leaves this as "Synapse LLC / QuickEnrich (or whatever Tom prefers)." If the executing agent has not received an explicit answer, default to `QuickEnrich` and add a note to the final summary asking Matt to confirm before flipping public.

- [ ] **Step 2: Write the LICENSE file**

```
MIT License

Copyright (c) 2026 QuickEnrich

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 3: Commit**

```bash
git add LICENSE
git commit -m "feat: add MIT license

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Write `CLAUDE.md` stub

**Files:**
- Create: `CLAUDE.md`

- [ ] **Step 1: Write the file**

Exact content:

```markdown
# Claude Code

This project uses [`AGENTS.md`](./AGENTS.md) as the single source of truth for
agent guidance. Open it for architecture, conventions, setup, and how to
swap providers.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add CLAUDE.md stub redirecting to AGENTS.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Write `AGENTS.md`

**Files:**
- Create: `AGENTS.md`

This is the largest doc. Goal: an agent reading this end-to-end after `git clone` can answer "what's in this repo, where does each tool's code live, which services does it call, how do I run it locally, how do I swap providers, how do I add a new tool" without reading any code.

**Required sections (in this order). Each must contain the listed facts.**

- [ ] **Step 1: Write `AGENTS.md` with all required sections**

Section list and exact required content:

1. **`# AGENTS.md` — top of file**
   One-paragraph project description: 6-tool lead-enrichment suite for quickenrich.io, monorepo of Next.js frontend + FastAPI/ARQ backend + Postgres schema + provider integrations.

2. **`## Quick map`**
   Bullet list of top-level directories and their purpose:
   - `backend/` — FastAPI app + ARQ workers (Python 3.11)
   - `frontend/` — Next.js 14 app (TypeScript, Tailwind, shadcn-style)
   - `database/` — Supabase Postgres schema and migrations
   - `docs/` — agent specs, plans, hosting and provider-swap guides
   - `docker-compose.yml` — local Postgres + Redis

3. **`## Architecture`**
   Request flow as numbered steps:
   1. User uploads CSV / fills form on `frontend/src/app/tools/<slug>/page.tsx`.
   2. Frontend posts to FastAPI router (`backend/app/routers/<name>.py`).
   3. Router enqueues ARQ job in Redis.
   4. ARQ worker (`backend/app/workers/<pipeline>.py`) runs the 5- or 6-phase pipeline (Discover → Resolve → Crawl → Extract → Enrich → Deliver).
   5. Each phase calls services in `backend/app/services/`.
   6. Results land in Postgres (`jobs`, `job_results` tables).
   7. CSV is generated, optionally emailed via Resend, downloadable via `backend/app/routers/download.py`.

4. **`## The tools`**
   Table with columns `slug | route | router | pipeline worker | discovery phase | services`. Rows for each of the 6 active tools (data sourced from `frontend/src/lib/tool-registry.ts`):
   - `company-location-finder` — `/tools/company-location-finder` — `routers/upload.py` — `workers/pipeline.py` — none (CSV in) — Serper
   - `company-intel` — `/tools/company-intel` — `routers/intel.py` — `workers/intel_pipeline.py` — none (URLs/names in) — Serper, Scrape.do, LLM, QuickEnrich
   - `g2-intel` — `/tools/g2-intel` — `routers/g2.py` — `workers/g2_pipeline.py` — `services/g2_scraper.py` + `services/g2_categories.py` — Serper, Scrape.do, LLM
   - `maps-intel` — `/tools/maps-intel` — `routers/maps.py` — `workers/maps_pipeline.py` — Serper /maps endpoint — Serper, Scrape.do, LLM
   - `funding-intel` — `/tools/funding-intel` — `routers/funding.py` — `workers/funding_pipeline.py` — `services/funding_discovery.py` (Serper /news + Gemini extraction) — Serper, Gemini, Scrape.do, LLM
   - `people-intel` — `/tools/people-intel` — `routers/people.py` — `workers/people_pipeline.py` — `services/linkedin_search.py` — Serper, QuickEnrich

5. **`## External services and their seams`**
   Single table mapping each provider to the file(s) where it's called:

   | Provider | Purpose | Primary file |
   |---|---|---|
   | Serper.dev | Google search (web + maps + news) | `backend/app/services/serper.py` |
   | Scrape.do | Anti-bot scraping proxy | `backend/app/services/scraper.py` |
   | Gemini / OpenAI | LLM extraction | `backend/app/services/llm/{base,gemini,openai_provider}.py` |
   | Supabase Postgres | Job + result storage | `backend/app/database.py` + `database/schema.sql` |
   | Resend | Result-delivery email | `backend/app/services/email_service.py` + `delivery.py` |
   | QuickEnrich | Named-contact enrichment | `backend/app/services/enrichment.py` |
   | Redis | Job queue + cache | `backend/app/services/cache.py` + ARQ in `workers/*` |

   "Single seam" sentence: each provider has exactly one primary file. To swap a provider, you change that file (or add a sibling) and update env vars. See `docs/swapping-providers.md`.

6. **`## Conventions`**
   - **Python**: Python 3.11, FastAPI async everywhere. SQLAlchemy 2.x async sessions. Pydantic settings in `backend/app/config.py`. `pytest` + `pytest-asyncio` for tests in `backend/tests/`. No blocking I/O in request handlers.
   - **TypeScript**: Next.js 14 App Router. **No `any` types** — anywhere. Tailwind + shadcn-style components in `frontend/src/components/`. SSE for live progress (`frontend/src/hooks/useSSE.ts`).
   - **Errors**: raise typed exceptions; let FastAPI's exception handlers convert. Don't swallow.
   - **Commits**: small, frequent. Conventional-commit prefixes (`feat:`, `fix:`, `chore:`, `docs:`).

7. **`## Running locally`**
   Numbered, copy-paste:
   ```
   git clone <your fork>
   cd <repo>

   # 1. Bring up Postgres + Redis
   docker compose up -d

   # 2. Backend
   cd backend
   python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   cp .env.example .env
   # Edit .env: paste at minimum SERPER_API_KEY, GEMINI_API_KEY, SCRAPE_DO_API_KEY
   uvicorn app.main:app --reload &
   arq app.workers.pipeline.WorkerSettings &

   # 3. Frontend (in a second terminal)
   cd ../frontend
   npm install
   cp .env.example .env.local
   npm run dev
   ```

8. **`## Deployment`**
   One paragraph: production runs on Railway (backend + Redis) + Vercel (frontend) + Supabase (Postgres) + Resend (email). For full instructions see [`docs/hosting.md`](docs/hosting.md). For alternatives (Fly, Neon, Postmark, etc.) see [`docs/swapping-providers.md`](docs/swapping-providers.md).

9. **`## Common tasks for an agent`**
   Each task gets 3-6 lines explaining the seam(s) to touch:

   - **Add a new tool** — create `frontend/src/app/tools/<slug>/page.tsx`, `frontend/src/app/tools/<slug>/README.md`, register in `frontend/src/lib/tool-registry.ts`, add `backend/app/routers/<name>.py`, add `backend/app/workers/<name>_pipeline.py` if it has a Phase 0, wire into `backend/app/main.py`.
   - **Add a new LLM provider** — drop a file in `backend/app/services/llm/` implementing the interface in `base.py`, register a factory clause where the provider is selected (search for `LLM_PROVIDER`), add a key to `backend/.env.example`.
   - **Change the email template** — `backend/app/services/email_service.py` + the templated HTML lives next to it.
   - **Swap a provider entirely** — see `docs/swapping-providers.md`.

10. **`## Pitfalls`**
    - Keep `JWT_SECRET` random in dev; not literally `change-me-in-production` (CI may flag).
    - Scrape.do is the difference between "10 results" and "all results" on G2 — without it, expect heavy fallback.
    - Funding-intel `/discover` endpoint is restricted to `hours=24|48` to prevent cache abuse — don't widen without considering cost.
    - Force-UTF-8 already enforced on QuickEnrich responses — don't strip that.

11. **`## Where things are written down`**
   - Specs: `docs/superpowers/specs/`
   - Plans: `docs/superpowers/plans/`
   - Hosting playbook: `docs/hosting.md`
   - Provider swaps: `docs/swapping-providers.md`
   - Per-tool README: `frontend/src/app/tools/<slug>/README.md`

- [ ] **Step 2: Verify all required facts are correct**

Run these checks and ensure each output matches:
```bash
ls backend/app/routers/    # confirm all referenced router files exist
ls backend/app/workers/    # confirm all referenced pipeline files exist
ls backend/app/services/llm/  # confirm base.py, gemini.py, openai_provider.py
grep -n 'NEXT_PUBLIC_API_URL' frontend/src/lib/tool-registry.ts  # confirm var name
```
If any reference in the AGENTS.md draft doesn't match, fix the draft.

- [ ] **Step 3: Commit**

```bash
git add AGENTS.md
git commit -m "docs: add AGENTS.md as primary cross-agent guidance

Single source of truth for agent context: architecture, the 6 tools and
their seams, conventions, local setup, and pointers to hosting and
swap-provider playbooks.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Write per-tool READMEs (×6)

**Files:**
- Create: `frontend/src/app/tools/company-location-finder/README.md`
- Create: `frontend/src/app/tools/company-intel/README.md`
- Create: `frontend/src/app/tools/g2-intel/README.md`
- Create: `frontend/src/app/tools/maps-intel/README.md`
- Create: `frontend/src/app/tools/funding-intel/README.md`
- Create: `frontend/src/app/tools/people-intel/README.md`

(`frontend/src/app/tools/website-finder/` is an inactive legacy artifact — see notes in spec. Do NOT add a README there; flag for follow-up cleanup in the final summary.)

**Required template — apply the same shape to all 6:**

```markdown
# <Tool Name>

<One paragraph: what the tool does, in user-facing terms.>

## User flow

1. <step 1>
2. <step 2>
3. <step 3>
…

## Backend

- **Route:** `<frontend route>`
- **Router:** `backend/app/routers/<name>.py`
- **Pipeline worker:** `backend/app/workers/<name>_pipeline.py`
- **Discovery phase (Phase 0):** `<service file or "none — input is uploaded directly">`
- **Services touched:** Serper, Scrape.do, LLM (gemini/openai), QuickEnrich (optional), Redis

## Notable design decisions

- <decision 1, e.g. "Uses user-provided Serper + QuickEnrich keys; backend pays for Scrape.do and LLM.">
- <decision 2 if applicable>

## Key files

- Frontend page: `frontend/src/app/tools/<slug>/page.tsx`
- Backend router: `backend/app/routers/<file>.py`
- Pipeline worker: `backend/app/workers/<file>.py`
- Discovery (if any): `backend/app/services/<file>.py`
```

- [ ] **Step 1: Write `company-location-finder/README.md`**

Use these exact facts (from memory + tool-registry):
- Description: "Find the exact company website by matching name and location. Upload a CSV with company names + cities/states; get back domain matches with confidence scoring."
- User flow: upload CSV → map company_name and location columns → confirm email → submit → wait for SSE progress → download CSV.
- Route: `/tools/company-location-finder`
- Router: `backend/app/routers/upload.py`
- Worker: `backend/app/workers/pipeline.py`
- Phase 0: none — input is the uploaded CSV.
- Services: Serper.
- Notable: location column improves match accuracy vs P1 (the original Website Finder) which had no location.

- [ ] **Step 2: Write `company-intel/README.md`**

Facts:
- Description: paste URLs or company names; Scrape.do crawls websites; LLM extracts industry, niche, description, target market, case studies, contacts.
- 5-phase pipeline: Resolve → Crawl → Extract → Enrich → Deliver.
- Route: `/tools/company-intel`
- Router: `backend/app/routers/intel.py`
- Worker: `backend/app/workers/intel_pipeline.py`
- Phase 0: none — input is URLs or company names directly.
- Services: Serper (resolve), Scrape.do (crawl), LLM (extract), QuickEnrich (enrich, optional).
- Notable: **user provides their own Serper and QuickEnrich keys**; backend pays for Scrape.do + LLM.

- [ ] **Step 3: Write `g2-intel/README.md`**

Facts:
- Description: select G2 software categories; the system scrapes G2 to discover listed products, then runs each through the company-intel pipeline.
- 6 phases (Phase 0 + 5 from intel pipeline).
- Route: `/tools/g2-intel`
- Router: `backend/app/routers/g2.py`
- Worker: `backend/app/workers/g2_pipeline.py`
- Phase 0: `backend/app/services/g2_scraper.py` (with category list in `services/g2_categories.py`).
- Services: Serper, Scrape.do, LLM. ~175 categories in static registry.
- Notable: G2 actively blocks scraping; Scrape.do unlocks the full ~80+ products per category vs ~10 from Google fallback.

- [ ] **Step 4: Write `maps-intel/README.md`**

Facts:
- Description: search Google Maps by category + location; discover businesses; run each through the company-intel pipeline.
- Route: `/tools/maps-intel`
- Router: `backend/app/routers/maps.py`
- Worker: `backend/app/workers/maps_pipeline.py`
- Phase 0: Serper `/maps` endpoint (no new dependency).
- Supports interactive mode and CSV upload with per-row locations.
- Notable: same Serper key as the rest; tile-grid expansion around seed centroid for higher coverage (`maps_expansion_max_tiles` in config).

- [ ] **Step 5: Write `funding-intel/README.md`**

Facts:
- Description: discovers companies funded in the last 24-48h via Serper /news + Gemini extraction; users browse/filter/select; selected companies feed into the company-intel pipeline.
- Route: `/tools/funding-intel`
- Router: `backend/app/routers/funding.py`
- Worker: `backend/app/workers/funding_pipeline.py`
- Phase 0: `backend/app/services/funding_discovery.py` — 3 parallel Serper /news queries → Gemini batch extraction (company_name, funding_amount, funding_round, lead_investor) → dedupe.
- Discovery cached for 1 hour. `/discover` endpoint restricted to `hours=24|48`.
- 6 visible phases: Discover → Resolve → Crawl → Extract → Enrich → Deliver.
- CSV includes funding metadata (company_name, funding_amount, funding_round, lead_investor, source_url, source_name) plus intel extraction columns.

- [ ] **Step 6: Write `people-intel/README.md`**

Facts:
- Description: paste/upload person names + company names → finds LinkedIn profiles + extracts business intelligence (uses lookup-by-name, not scraping; single contact CSV).
- Route: `/tools/people-intel`
- Router: `backend/app/routers/people.py`
- Worker: `backend/app/workers/people_pipeline.py`
- Phase 0: `backend/app/services/linkedin_search.py`.
- Services: Serper, QuickEnrich.
- Notable: looks up by name (no scraping); produces a single-contact CSV.

- [ ] **Step 7: Verify all six files exist and have the same shape**

Run:
```bash
for slug in company-location-finder company-intel g2-intel maps-intel funding-intel people-intel; do
  echo "=== $slug ==="
  ls "frontend/src/app/tools/$slug/README.md" || echo MISSING
  head -1 "frontend/src/app/tools/$slug/README.md"
done
```
Expected: all 6 files exist; each starts with `# `.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/app/tools/*/README.md
git commit -m "docs: per-tool READMEs colocated with each tool

One README per active tool with consistent shape: description, user flow,
backend wiring, notable design decisions, key files. Colocated so future
tool changes touch the README in the same diff.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Write root `README.md`

**Files:**
- Create or replace: `README.md`

(If a README already exists, read it first and fold any non-redundant content forward.)

- [ ] **Step 1: Check for existing README**

Run: `ls README.md 2>/dev/null && head -40 README.md`. Note any current content to preserve.

- [ ] **Step 2: Write the new `README.md`**

Required structure and content:

```markdown
# QuickEnrich Tools

A free, open-source suite of 6 lead-enrichment tools you can clone, run on
your own laptop with your own API keys, customize with your favorite AI
coding agent, and (optionally) self-host for your team.

**Live demo:** https://quick-enrich-tools.vercel.app

![Tool grid screenshot](docs/assets/screenshot.png)
<!-- The screenshot is optional. If docs/assets/screenshot.png isn't
created, remove the image line. -->

## What's included

| Tool | What it does |
|---|---|
| **Company + Location Website Finder** | CSV in, verified company domains out — uses location for accuracy |
| **Company / People Intel by URL** | Paste URLs or company names → industry, target market, case studies, contacts |
| **G2 Category → Company Intel** | Pick G2 software categories → discover companies → enrich each |
| **Google Maps → Company Intel** | Search Maps by category + location → discover businesses → enrich each |
| **Funded Companies Today** | Discovers companies funded in the last 24-48h, lets you select, enriches |
| **People Intel by Name** | Names + companies → LinkedIn + intel |

## Run it locally in 5 minutes

```bash
git clone https://github.com/<your-handle>/quickenrich-tools.git
cd quickenrich-tools

# 1. Local Postgres + Redis
docker compose up -d

# 2. Backend (terminal 1)
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: paste your SERPER_API_KEY, GEMINI_API_KEY, SCRAPE_DO_API_KEY
uvicorn app.main:app --reload &
arq app.workers.pipeline.WorkerSettings &

# 3. Frontend (terminal 2)
cd ../frontend
npm install
cp .env.example .env.local
npm run dev
```

Open http://localhost:3000 — the tool grid loads. Pick a tool and try it.

## What it costs (running it yourself)

You bring your own keys. The repo authors don't see any of it.

| Service | Required? | Cost |
|---|---|---|
| [Serper](https://serper.dev) | yes | free tier 2.5k searches; $50/mo for 50k |
| [Gemini](https://ai.google.dev) (or OpenAI) | yes | free tier covers small runs |
| [Scrape.do](https://scrape.do) | strongly recommended | $29/mo entry tier |
| [QuickEnrich](https://quickenrich.io) | optional | per-request |
| Postgres + Redis | yes | free via docker-compose |

## Want to host it for your team?

The reference stack is Railway + Vercel + Supabase + Resend (~$20-40/mo for a small team). See [`docs/hosting.md`](docs/hosting.md) for full deployment instructions, plus alternatives (Fly, Render, Neon, Firebase, etc.).

## Customizing for your stack

This repo is designed to be forked and customized. Use any AI coding agent (Claude Code, Codex, Cursor, Aider) to swap providers — Supabase for Neon, Railway for Fly, Scrape.do for SpiderCloud, whatever.

See [`docs/swapping-providers.md`](docs/swapping-providers.md) for tiered playbooks. Each section ends with a copy-paste prompt you can hand to your agent.

## Open it in your agent

```bash
# Claude Code
claude

# Codex CLI
codex

# Cursor
cursor .
```

All three read [`AGENTS.md`](./AGENTS.md), which is the single source of truth for architecture, conventions, and where everything lives.

## Architecture (one paragraph)

Next.js frontend (Vercel-friendly) talks to a FastAPI backend (Python 3.11) which dispatches jobs to ARQ workers backed by Redis. Each tool runs a multi-phase pipeline (Discover → Resolve → Crawl → Extract → Enrich → Deliver) calling external services (Serper, Scrape.do, LLM, QuickEnrich) and storing results in Postgres. CSVs are emailed via Resend or downloaded directly.

For the full architecture deep-dive, read [`AGENTS.md`](./AGENTS.md).

## Contributing

Issues and PRs welcome. Please read [`AGENTS.md`](./AGENTS.md) before opening a PR — it's also a great human onboarding doc.

## License

MIT — see [`LICENSE`](./LICENSE).

## Credits

Built by [QuickEnrich](https://quickenrich.io). The hosted version of these tools (free) lives at https://quick-enrich-tools.vercel.app.
```

- [ ] **Step 3: Verify links resolve**

Run:
```bash
for f in AGENTS.md LICENSE docs/hosting.md docs/swapping-providers.md; do
  test -f "$f" && echo "OK: $f" || echo "MISSING: $f"
done
```
At this point in the plan, `AGENTS.md` and `LICENSE` should exist. `docs/hosting.md` and `docs/swapping-providers.md` come in later tasks — note any MISSING and ensure they're created before the public flip.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: rewrite README for public release with local-first framing

Leads with local-mode 5-min quickstart. Hosted-deploy and provider-swap
playbooks live in docs/. Links to AGENTS.md as the agent-readable single
source of truth.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Write `docs/hosting.md`

**Files:**
- Create: `docs/hosting.md`

- [ ] **Step 1: Write the file**

Required sections (with concrete content):

```markdown
# Hosting QuickEnrich for a Team

The local-first instructions in [`README.md`](../README.md) are enough for one
user on one laptop. If you want a deployed version your team can hit from a
URL, this is the playbook.

## Reference stack

This is what quickenrich.io itself runs on:

| Layer | Service | Cost |
|---|---|---|
| Backend (FastAPI + ARQ worker) | [Railway](https://railway.app) | ~$10/mo |
| Frontend (Next.js) | [Vercel](https://vercel.com) | free |
| Postgres | [Supabase](https://supabase.com) | free for small teams |
| Redis (queue + cache) | Railway Redis add-on | included with Railway |
| Email (CSV delivery) | [Resend](https://resend.com) | free 3k/mo |

**Total: ~$10-20/mo.** A small team running a few hundred enrichments/day
fits in this budget. Want a different stack? See
[`swapping-providers.md`](swapping-providers.md).

## Step-by-step deploy (reference stack)

### 1. Postgres on Supabase

1. Sign up at [supabase.com](https://supabase.com), create a project.
2. Open the SQL editor, paste the contents of `database/schema.sql`, run.
3. Settings → Database → copy the **connection string** (use the `Connection pooling` URL with `?pgbouncer=true` mode for serverless tolerance, or the direct URL for Railway). You'll need this as `DATABASE_URL`.
4. (Optional) Enable Row-Level Security in Authentication → Policies if you plan to use Supabase Auth.

### 2. Redis on Railway (with the backend)

1. Sign up at [railway.app](https://railway.app).
2. New Project → Deploy from GitHub Repo → pick your fork.
3. Railway will auto-detect Python and run `Procfile`. Add a Redis service from the New → Database → Redis menu.
4. Railway auto-provisions `REDIS_URL` to your service.

### 3. Backend on Railway

In the Railway dashboard, add these env vars (Variables tab):

```
DATABASE_URL=<from Supabase>
REDIS_URL=<auto-provisioned by Railway>
JWT_SECRET=<run: openssl rand -hex 32>
SERPER_API_KEY=<your key>
GEMINI_API_KEY=<your key>     # or OPENAI_API_KEY
LLM_PROVIDER=gemini
SCRAPE_DO_API_KEY=<your key>
RESEND_API_KEY=<your key>
QUICKENRICH_API_KEY=<your key>  # optional
STORAGE_BUCKET=quickenrich-results
FRONTEND_URL=<your Vercel URL>
```

Railway redeploys on every git push to your main branch.

**Important:** Railway by default runs only `web` from `Procfile`. The ARQ worker needs its own service. Either:
- Add a second Railway service pointing at the same repo with start command `arq app.workers.pipeline.WorkerSettings`, OR
- Run a single process that starts both (requires editing `Procfile` to use a process manager — out of scope here, see swapping-providers for Fly).

### 4. Frontend on Vercel

1. `vercel --prod` from the `frontend/` directory, OR import the GitHub repo from the Vercel dashboard with **Root Directory** set to `frontend`.
2. Vercel env: `NEXT_PUBLIC_API_URL=<your Railway backend URL>`.
3. Point a custom domain at Vercel.

### 5. Email on Resend

1. Sign up at [resend.com](https://resend.com), verify a sending domain.
2. Generate an API key, paste into Railway as `RESEND_API_KEY`.
3. Update the `from:` address in `backend/app/services/email_service.py` if needed.

### 6. Smoke test the deploy

Submit a CSV to Company Location Finder, watch progress in the UI, confirm the email arrives, confirm the CSV downloads.

## Local mode vs. hosted mode

| Need | Local | Hosted |
|---|---|---|
| One user, occasional runs | ✅ | overkill |
| Team-wide access | ❌ | ✅ |
| Long-running jobs (close laptop) | ❌ | ✅ |
| Email delivery of CSVs | possible | natural |
| Auth / per-user history | manual | natural |

A reasonable path: start local. When you find yourself running it daily or a teammate asks for access, deploy.

## Want a different stack?

[`swapping-providers.md`](swapping-providers.md) has playbooks for:
- Database: Supabase → Neon, Postgres anywhere, Firebase
- Backend hosting: Railway → Fly.io, Render, self-hosted Docker
- Scraping: Scrape.do → SpiderCloud, Apify, Bright Data
- LLM: Gemini ↔ OpenAI ↔ Anthropic
- Email: Resend → Postmark, SendGrid
- Frontend: Vercel → Netlify, Cloudflare Pages
```

- [ ] **Step 2: Verify referenced files exist**

Run:
```bash
test -f database/schema.sql && echo "OK schema" || echo "MISSING schema"
test -f backend/Procfile && echo "OK Procfile" || echo "MISSING Procfile"
grep -n 'from:' backend/app/services/email_service.py | head -3
```
Fix any hosting.md text that doesn't match reality.

- [ ] **Step 3: Commit**

```bash
git add docs/hosting.md
git commit -m "docs: add hosting.md for team-deploy playbook

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: Write `docs/swapping-providers.md`

**Files:**
- Create: `docs/swapping-providers.md`

This is tiered. Tier 1 swaps get full playbooks. Tier 2 get medium recipes. Tier 3 get one-paragraph pointers. Every section ends with a **copy-paste agent prompt**.

- [ ] **Step 1: Write the file**

Required structure (reproduce in full):

```markdown
# Swapping Providers

The reference stack (Railway + Vercel + Supabase + Resend + Scrape.do +
Gemini) is one option. None of it is load-bearing in the *code* — every
external dependency lives in a single seam you can swap.

This guide is tiered by effort:
- **Tier 1** — significant work but well-bounded
- **Tier 2** — moderate work, single-file
- **Tier 3** — drop-in, near zero work

Every section ends with a prompt you can paste into Claude Code, Codex, or
Cursor to do the swap with you.

---

## Tier 1: Significant swaps

### Database: Supabase → Neon (or Postgres anywhere)

**Why this is straightforward:** the code only depends on Postgres-compatible SQL via SQLAlchemy. Supabase is just a Postgres host; Neon, RDS, Cloud SQL, or self-hosted Postgres work identically.

**Files to touch:**
- `backend/.env` → swap `DATABASE_URL` to your new Postgres connection string.
- `database/schema.sql` → run this once on your new DB. Use `psql "$DATABASE_URL" < database/schema.sql` or your provider's SQL editor.
- `backend/app/database.py` → no change needed for vanilla Postgres. If your provider needs SSL or specific pool args, they go here (line 11).

**Auth note:** if you were using Supabase Auth, Neon doesn't bundle auth — pick Auth0, Clerk, or roll your own JWT. Backend already has JWT setup at `backend/app/auth.py`.

**Test:**
1. `docker compose down` (stop local Postgres if running)
2. Update `.env` with new `DATABASE_URL`
3. `cd backend && uvicorn app.main:app --reload`
4. Submit a small job through the UI; confirm it persists (`SELECT * FROM jobs LIMIT 5`).

**Agent prompt:**
> Swap Postgres host from local docker-compose to Neon. The seam is `DATABASE_URL` in `backend/.env`. Run `database/schema.sql` against the new database. Verify by submitting a small job and confirming a row lands in the `jobs` table.

### Database: Supabase → Firebase (Firestore)

**Honest warning:** Firebase Firestore is document-oriented. The current schema uses joins (`jobs` ↔ `job_results`). A direct port means rewriting `backend/app/database.py` and every query against `models.py`. This is a real refactor, not a config change.

**If you still want it:**
- Replace SQLAlchemy with the Firebase Admin SDK in `backend/app/database.py`.
- Convert `models.py` from SQLAlchemy ORM to Firestore document classes.
- Each query in routers and workers needs rewriting (`session.execute(select(...))` → `firestore_client.collection(...).where(...)`).
- ARQ stays the same — Redis is independent.

**Recommendation:** unless you're already a Firebase shop, stay on Postgres (Neon is free).

**Agent prompt:**
> I want to migrate this codebase from Postgres to Firebase Firestore. Read `backend/app/database.py`, `backend/app/models.py`, and every router/worker file. Plan the rewrite — I want a list of every file you'd touch and a rough line-count estimate before any code changes.

### Backend hosting: Railway → Fly.io / Render / self-hosted Docker

**Files relevant to deploy:** `backend/Procfile`, `backend/requirements.txt`, `backend/runtime.txt`, repo root for any `Dockerfile`.

**Fly.io:** add a `backend/Dockerfile` (FROM python:3.11-slim, COPY, pip install, CMD uvicorn). Add `backend/fly.toml`:

```toml
app = "your-app-name"
primary_region = "iad"

[http_service]
  internal_port = 8000
  force_https = true
  auto_stop_machines = true
  auto_start_machines = true

[[services]]
  internal_port = 8000
  protocol = "tcp"

[processes]
  web = "uvicorn app.main:app --host 0.0.0.0 --port 8000"
  worker = "arq app.workers.pipeline.WorkerSettings"
```

`fly launch` from `backend/`, then `fly secrets set DATABASE_URL=… SERPER_API_KEY=…`.

**Render:** add a `render.yaml` at repo root with two services (web + worker) sharing env. Render auto-provisions Postgres + Redis if you want to colocate; otherwise point at Supabase + Upstash.

**Self-hosted Docker:** write a `Dockerfile` (same as Fly's) plus a `compose.prod.yml` that adds the backend service to the existing `docker-compose.yml`. Front it with Caddy or Nginx for TLS.

**Agent prompt:**
> Switch backend hosting from Railway to Fly.io. Read `backend/Procfile` and `backend/requirements.txt`. Create `backend/Dockerfile` and `backend/fly.toml` with web + worker processes. Document the `fly secrets set` commands needed. Do not delete Railway-specific files (`Procfile`, `railway.toml`) — leave them for users who stay on Railway.

---

## Tier 2: Single-file swaps

### Scraping: Scrape.do → SpiderCloud / Apify / Bright Data

**Single seam:** `backend/app/services/scraper.py`. The current implementation builds a Scrape.do URL like:
```
https://api.scrape.do/?token={SCRAPE_DO_API_KEY}&url={target_url}&render=false
```

**SpiderCloud equivalent:** their proxy endpoint format is documented at https://spider.cloud/docs/api. Replace the URL builder. Keep the `httpx.AsyncClient` and retry/timeout machinery.

**Apify equivalent:** different model — you call an actor and poll for results. Wrap that polling in the same async function signature `async def fetch(url) -> str` so the rest of the pipeline doesn't change.

**Bright Data equivalent:** they offer a proxy you set as the `httpx` proxy URL. Lighter swap: point `httpx.AsyncClient(proxies=...)` at Bright Data's URL and drop the Scrape.do URL building entirely.

**Test:** run G2 Intel against a small category (e.g. `product-analytics --max 5`); confirm 5 product pages scrape successfully.

**Agent prompt:**
> Swap the scraping provider in `backend/app/services/scraper.py` from Scrape.do to <SpiderCloud | Apify | Bright Data>. Preserve the `async def fetch(url) -> str` signature so callers don't change. Update `backend/.env.example` to swap `SCRAPE_DO_API_KEY` for the new provider's env. Add a 1-line comment at the top of `scraper.py` saying which provider this build uses.

### LLM: Gemini ↔ OpenAI ↔ Anthropic

**Already abstracted:** `backend/app/services/llm/base.py` defines the interface; `gemini.py` and `openai_provider.py` implement it. The provider is selected at runtime by `LLM_PROVIDER` env.

**Adding Anthropic:**
1. Create `backend/app/services/llm/anthropic_provider.py` — implement the same interface as `gemini.py`.
2. Find the factory site (search for `LLM_PROVIDER == "gemini"`) and add an `elif LLM_PROVIDER == "anthropic"` clause.
3. Add `ANTHROPIC_API_KEY=` to `backend/.env.example`.
4. Add `anthropic==0.x` to `backend/requirements.txt`.

**Test:** `LLM_PROVIDER=anthropic` in `.env`, restart backend, submit a Company Intel job, confirm extraction completes.

**Agent prompt:**
> Add Anthropic Claude as a third LLM provider in `backend/app/services/llm/`. Mirror the structure of `gemini.py` and `openai_provider.py`. Update the factory clause where `LLM_PROVIDER` is read. Add the env var and the SDK to `requirements.txt`. End with a smoke test plan.

---

## Tier 3: Drop-in swaps

### Email: Resend → Postmark / SendGrid

Single seam: `backend/app/services/email_service.py`. Replace the Resend SDK call with the new provider's SDK. Update env var name. ~10 lines of code change.

### Frontend hosting: Vercel → Netlify / Cloudflare Pages

Next.js 14 deploys cleanly to both. For Netlify, install `@netlify/plugin-nextjs` and add a `netlify.toml`. For Cloudflare, use `@cloudflare/next-on-pages`. Env var moves with you.

### Search: Serper → SerpApi / Google Custom Search

Single seam: `backend/app/services/serper.py`. URL pattern + auth header changes. Output schema matches between Serper and SerpApi closely.

### Redis: Railway Redis → Upstash / self-hosted

`REDIS_URL` env change only. Upstash provides a Redis-compatible URL. ARQ doesn't care about the host.

---

## Common pitfalls

- **Forgetting the worker process.** Some swaps (especially Railway → other) lose the ARQ worker if you only deploy the web process. Symptom: jobs queue up but never run.
- **CORS.** Changing the frontend domain means updating CORS allowlist in `backend/app/main.py` (search for `CORSMiddleware`).
- **Email sending domain.** Switching email providers requires re-verifying your sending domain. Plan for SPF/DKIM DNS propagation.
- **Schema drift.** If you swap databases, the schema must be applied to the new DB before the backend will boot.
```

- [ ] **Step 2: Verify file references match codebase reality**

Run:
```bash
grep -n 'scrape.do' backend/app/services/scraper.py | head -3
grep -n 'LLM_PROVIDER' backend/app/services/llm/*.py | head -10
test -f backend/app/services/llm/base.py && echo OK
test -f backend/app/services/email_service.py && echo OK
test -f backend/app/main.py && grep -n CORSMiddleware backend/app/main.py
```
Fix any references in the swapping-providers draft that don't match.

- [ ] **Step 3: Commit**

```bash
git add docs/swapping-providers.md
git commit -m "docs: add tiered provider-swap playbook

Tier 1 (DB, backend host) full playbooks; Tier 2 (scraping, LLM) recipes;
Tier 3 (email, frontend host, search, redis) pointers. Every section ends
with an agent-ready prompt.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: Verify pre-flight gate (USER ACTION)

**Files:** none — gate task.

- [ ] **Step 1: Confirm with the user that all 4 keys have been rotated**

Ask the user explicitly: "Have you rotated Serper, Gemini, OpenAI, and QuickEnrich keys, updated Railway, and confirmed the running app still works?"

If anything is "not yet," **stop here**. Do not proceed to Task 13. The remaining tasks rewrite git history; running them before rotation is fine, but flipping public before rotation leaks the live keys.

- [ ] **Step 2: Mark verified**

Once the user confirms, proceed to Task 13.

---

## Task 13: Scrub leaked-key blob from git history

**Files:** rewrites all of git history. No working-tree files change.

**Tooling:** `git filter-repo` is the modern replacement for `git filter-branch`. Install:
```bash
pip install git-filter-repo   # or: brew install git-filter-repo
```

- [ ] **Step 1: Make a backup mirror clone (safety)**

```bash
cd ..
git clone --mirror QuickEnrich QuickEnrich-pre-scrub-backup.git
cd QuickEnrich
```
The backup lives next to the working repo. Keep it until the public flip is verified.

- [ ] **Step 2: Build the replacements file**

Write a temp file `scrub-replacements.txt` (don't commit) with one regex per line — these are the literal leaked values:

```
REDACTED_SERPER_KEY==>REDACTED_SERPER_KEY
REDACTED_GEMINI_KEY==>REDACTED_GEMINI_KEY
REDACTED_OPENAI_KEY==>REDACTED_OPENAI_KEY
REDACTED_QUICKENRICH_KEY==>REDACTED_QUICKENRICH_KEY
```

- [ ] **Step 3: Run filter-repo**

```bash
git filter-repo --replace-text scrub-replacements.txt --force
```
`--force` is required because filter-repo refuses to run on a repo that isn't a fresh clone; you've made the backup, so this is fine.

- [ ] **Step 4: Delete the replacements file**

```bash
rm scrub-replacements.txt
```

- [ ] **Step 5: Verify the leaked strings are gone from history**

```bash
git log --all -p > /tmp/post_scrub.txt
grep -c 'REDACTED_SERPER_KEY\|REDACTED_GEMINI_KEY\|REDACTED_OPENAI_KEY_FRAGMENT\|REDACTED_QUICKENRICH_KEY' /tmp/post_scrub.txt
rm /tmp/post_scrub.txt
```
Expected: `0` matches.

- [ ] **Step 6: filter-repo removed origin — re-add it**

filter-repo strips remotes by design (forces you to think before pushing). Re-add:
```bash
git remote add origin git@github.com:<your-handle>/quickenrich-tools.git
# Or if HTTPS:
# git remote add origin https://github.com/<your-handle>/quickenrich-tools.git
```

- [ ] **Step 7: NO commit needed** — filter-repo has already rewritten history.

---

## Task 14: Final secrets sweep

**Files:** none — verification only.

- [ ] **Step 1: Run a comprehensive secrets scan**

```bash
git log --all -p > /tmp/full_history.txt
grep -nE '(sk-proj-|sk_live_|sk_test_[A-Za-z0-9]{20,}|re_[A-Za-z0-9]{20,}|AIza[A-Za-z0-9_-]{30,}|REDACTED_SERPER_KEY_FRAGMENT|eyJ[A-Za-z0-9_-]{40,})' /tmp/full_history.txt | grep -v REDACTED | head -20
rm /tmp/full_history.txt
```
Expected: empty output. Any hit means a key was missed; investigate before proceeding.

- [ ] **Step 2: Optional — run `gitleaks` if installed**

```bash
which gitleaks && gitleaks detect --source=. --no-banner || echo "gitleaks not installed (optional)"
```
If installed, expect zero leaks. If unavailable, skip.

---

## Task 15: Add landing-page GitHub CTA

**Files:**
- Modify: `frontend/src/app/page.tsx` (add GitHub link in nav and a section near the bottom)
- Possibly create: `frontend/src/components/GithubBanner.tsx`

- [ ] **Step 1: Read current `page.tsx` to find the right insertion points**

Run: `cat frontend/src/app/page.tsx`. Identify the top nav (or top-right corner icons) and the bottom of the main content.

- [ ] **Step 2: Add GitHub icon to top nav**

Inside whatever JSX renders the top nav/header (or, if there's no nav, the top-right of the hero), add a link:

```tsx
<a
  href="https://github.com/<your-handle>/quickenrich-tools"
  target="_blank"
  rel="noopener noreferrer"
  className="text-muted-foreground hover:text-primary transition-colors"
  aria-label="View source on GitHub"
>
  <Github className="w-5 h-5" />
</a>
```

Import: `import { Github } from "lucide-react";` (already a project dependency — confirmed in `package.json`).

- [ ] **Step 3: Add a "Get the source" section near the bottom**

Just before the closing `</main>` (or whatever the homepage's outer container is), insert:

```tsx
<section className="container mx-auto px-4 py-16 border-t border-border/40">
  <div className="max-w-2xl mx-auto text-center space-y-4">
    <h2 className="text-2xl font-semibold">Open source. Clone it.</h2>
    <p className="text-muted-foreground">
      Every tool here is in a public repo you can clone, customize with
      Claude Code or any other AI agent, and self-host on your own stack —
      Supabase, Neon, Firebase, Railway, Fly, Vercel, Netlify, your call.
    </p>
    <pre className="bg-muted text-sm p-4 rounded-lg overflow-x-auto text-left max-w-xl mx-auto">
      <code>git clone https://github.com/&lt;your-handle&gt;/quickenrich-tools.git</code>
    </pre>
    <a
      href="https://github.com/<your-handle>/quickenrich-tools"
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:opacity-90 transition-opacity"
    >
      <Github className="w-4 h-4" />
      Get the source on GitHub
      <ArrowRight className="w-4 h-4" />
    </a>
  </div>
</section>
```

The `Github` icon is already in `lucide-react`; `ArrowRight` already imported on this page (verified in current `page.tsx`).

- [ ] **Step 4: Replace `<your-handle>` placeholder**

Once the user confirms the final GitHub repo URL, replace both occurrences of `https://github.com/<your-handle>/quickenrich-tools` with the real URL.

- [ ] **Step 5: Test locally**

```bash
cd frontend && npm run dev
```
Visit http://localhost:3000, confirm the icon shows in the nav and the "Open source. Clone it." section renders cleanly. Click both links — they should open the GitHub repo.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/page.tsx
git commit -m "feat(frontend): add GitHub CTA to landing page

Top-nav icon plus a 'Open source. Clone it.' section near the bottom of
the homepage with a one-paragraph pitch and the clone command.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 16: Push rewritten history and flip the repo public

**Files:** GitHub repo settings — done via `gh` CLI or the dashboard.

- [ ] **Step 1: Force-push the rewritten history**

```bash
git push origin main --force-with-lease
```
`--force-with-lease` is safer than `--force` — it refuses if the remote has commits the local doesn't (impossible here since you're the only contributor, but cheap insurance).

If origin doesn't exist yet (filter-repo stripped it; Task 13 step 6 re-added it), confirm: `git remote -v`.

- [ ] **Step 2: Flip repo visibility to public**

Via `gh`:
```bash
gh repo edit <your-handle>/quickenrich-tools --visibility public --accept-visibility-change-consequences
```
Or via the GitHub dashboard: Settings → General → Danger Zone → Change visibility → Public.

- [ ] **Step 3: Set repo description and topics**

```bash
gh repo edit <your-handle>/quickenrich-tools \
  --description "Open-source lead enrichment tool suite — 6 free tools you can clone, customize, and self-host." \
  --add-topic lead-enrichment \
  --add-topic nextjs \
  --add-topic fastapi \
  --add-topic claude-code \
  --add-topic agents-md \
  --add-topic supabase \
  --add-topic web-scraping \
  --add-topic b2b
```

- [ ] **Step 4: Upload social-preview image (manual)**

In the GitHub web UI: Settings → Social preview → Upload — use a screenshot of the tool grid from quick-enrich-tools.vercel.app. (Skip if no screenshot is available; can be added later.)

- [ ] **Step 5: Pin a welcome issue (manual or via gh)**

```bash
gh issue create --title "Welcome — start with AGENTS.md" --body "If you just cloned this repo and are here to customize: open AGENTS.md. It's the entry point for any AI coding agent (Claude Code, Codex, Cursor) and the human-readable architecture doc.

To run locally in 5 minutes: see the README. To deploy to your own infra: see docs/hosting.md. To swap providers: see docs/swapping-providers.md."
gh issue pin <issue-number>
```

---

## Task 17: Smoke test — clone the public repo and run local mode

**Files:** none in the working repo. Tests an external clone.

- [ ] **Step 1: Clone fresh into a temp directory**

```bash
cd /tmp   # or any disposable parent dir
rm -rf qe-smoketest
git clone https://github.com/<your-handle>/quickenrich-tools.git qe-smoketest
cd qe-smoketest
```

- [ ] **Step 2: Follow the README local-mode steps verbatim**

Don't deviate — the README is what new users will read.

```bash
docker compose up -d

cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Paste a real Serper key + Gemini key + Scrape.do key into .env (these can
# be your personal keys; this is just a smoke test).
uvicorn app.main:app --reload &
arq app.workers.pipeline.WorkerSettings &

cd ../frontend
npm install
cp .env.example .env.local
npm run dev
```

Open http://localhost:3000 in a browser.

- [ ] **Step 3: Run one tool end-to-end**

Pick Company Location Finder (the simplest pipeline). Upload a 2-row CSV, confirm:
- Upload completes.
- SSE progress updates land in the UI.
- Result appears in the UI / downloadable.

If anything is broken, the README is wrong — fix the README, push, retest.

- [ ] **Step 4: Cleanup**

```bash
docker compose down
cd /tmp && rm -rf qe-smoketest
```

- [ ] **Step 5: Final summary to user**

Report:
- Public repo URL
- License confirmation (MIT — copyright "QuickEnrich" or whatever Matt confirmed)
- Backup mirror location (`../QuickEnrich-pre-scrub-backup.git`) and recommendation to keep until at least one external collaborator confirms a clean clone, then delete.
- Any items deferred (e.g. social-preview image, future cleanup of `frontend/src/app/tools/website-finder/`).

---

## Self-Review Notes

Spec coverage check (mapping each spec deliverable to a task):

| Spec deliverable | Task |
|---|---|
| AGENTS.md | 7 |
| CLAUDE.md stub | 6 |
| README.md | 9 |
| Per-tool READMEs | 8 |
| docs/hosting.md | 10 |
| docs/swapping-providers.md | 11 |
| docker-compose.yml | 2 |
| .env.example audit | 3 + 4 |
| LICENSE | 5 |
| Landing-page CTA | 15 |
| Delete standalone/g2-intel | 1 |
| GitHub repo metadata | 16 (description, topics, social, pin) |
| Pre-flight: rotate keys | 12 (gate) — user action |
| Pre-flight: scrub history | 13 |
| Final secrets sweep | 14 |
| Push + flip public | 16 |
| Smoke test | 17 |

All spec deliverables covered.

**Type/name consistency check:** AGENTS.md table refers to `g2-intel` workers and routers; verified against `backend/app/routers/g2.py` and `backend/app/workers/g2_pipeline.py`. The `frontend/src/app/tools/website-finder/` directory exists but is NOT in the active `tools` registry — flagged in Task 8 introduction as future cleanup, not added in this plan.

**Placeholder scan:** `<your-handle>` appears 6 times — these are explicit user-action placeholders the executor must replace with the real GitHub username/org before the public flip. Marked with the literal angle brackets to make them grep-able.
