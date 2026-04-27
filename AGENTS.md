# AGENTS.md

QuickEnrich is an open-source suite of 6 lead-enrichment tools for
[quickenrich.io](https://quickenrich.io). Monorepo: Next.js frontend +
FastAPI/ARQ backend + Postgres schema + integrations to a small handful of
external services. This file is the single source of truth for any AI
coding agent (Claude Code, Codex, Cursor, Aider) working in the repo.
Read it end-to-end before making changes.

## Quick map

- `backend/` — FastAPI app + ARQ workers (Python 3.11)
- `frontend/` — Next.js 14 App Router (TypeScript, Tailwind, shadcn-style)
- `database/` — Postgres schema (`schema.sql`) and migrations
- `docs/` — design specs, implementation plans, hosting and provider-swap guides
- `docker-compose.yml` — local Postgres + Redis (so `npm run dev` and `uvicorn` can run on the host)

## Architecture

The request flow for any tool:

1. User uploads a CSV or fills a form on `frontend/src/app/tools/<slug>/page.tsx`.
2. Frontend posts to a FastAPI router under `backend/app/routers/<name>.py`.
3. Router enqueues an ARQ job in Redis.
4. ARQ worker (`backend/app/workers/<pipeline>.py`) runs the pipeline:
   - Discover (Phase 0, only some tools) → Resolve → Crawl → Extract → Enrich → Deliver.
5. Each phase calls service modules in `backend/app/services/`.
6. Results land in Postgres in the `jobs` and `job_results` tables.
7. The CSV is generated, optionally emailed via Resend, and downloadable via `backend/app/routers/download.py`.

Frontend ↔ backend live progress is via Server-Sent Events; client hook is `frontend/src/hooks/useSSE.ts`.

## The tools

| Slug | Frontend route | Router | Pipeline worker | Discovery (Phase 0) | Services |
|---|---|---|---|---|---|
| `company-location-finder` | `/tools/company-location-finder` | `routers/upload.py` | `workers/pipeline.py` | none — input is uploaded CSV | Serper |
| `company-intel` | `/tools/company-intel` | `routers/intel.py` | `workers/intel_pipeline.py` | none — input is URLs/names | Serper, Scrape.do, LLM, QuickEnrich |
| `g2-intel` | `/tools/g2-intel` | `routers/g2.py` | `workers/g2_pipeline.py` | `services/g2_scraper.py` (+ `services/g2_categories.py`) | Serper, Scrape.do, LLM |
| `maps-intel` | `/tools/maps-intel` | `routers/maps.py` | `workers/maps_pipeline.py` | Serper `/maps` endpoint (no new dep) | Serper, Scrape.do, LLM |
| `funding-intel` | `/tools/funding-intel` | `routers/funding.py` | `workers/funding_pipeline.py` | `services/funding_discovery.py` (Serper `/news` + Gemini extraction) | Serper, Gemini, Scrape.do, LLM |
| `people-intel` | `/tools/people-intel` | `routers/people.py` | `workers/people_pipeline.py` | `services/linkedin_search.py` | Serper, QuickEnrich |

Per-tool deep-dives live in each tool's directory: `frontend/src/app/tools/<slug>/README.md`.

> Note: `frontend/src/app/tools/website-finder/` exists but is **not** registered in `frontend/src/lib/tool-registry.ts` and is not surfaced on the homepage. It's a legacy artifact (the original Product 1, built separately by the client). Treat as inert.

## External services and their seams

| Provider | Purpose | Primary file |
|---|---|---|
| Serper.dev | Google search (web + maps + news) | `backend/app/services/serper.py` |
| Scrape.do | Anti-bot scraping proxy | `backend/app/services/scraper.py` |
| Gemini / OpenAI | LLM extraction | `backend/app/services/llm/{base,gemini,openai_provider}.py`; factory in `backend/app/services/llm/__init__.py` |
| Postgres (Supabase / Neon / anywhere) | Job + result storage | `backend/app/database.py` + `database/schema.sql` |
| Resend | Result-delivery email | `backend/app/services/email_service.py` (called by `delivery.py`) |
| QuickEnrich | Named-contact enrichment | `backend/app/services/enrichment.py` |
| Redis | ARQ job queue + cache | `backend/app/services/cache.py` + ARQ in `workers/*` |

Each provider has exactly one primary file. To swap a provider, change that
file (or add a sibling) and update env vars. See
[`docs/swapping-providers.md`](docs/swapping-providers.md).

## Conventions

**Python (backend):**
- Python 3.11. FastAPI async everywhere; no blocking I/O in request handlers.
- SQLAlchemy 2.x async sessions (`backend/app/database.py`).
- Pydantic settings for all config (`backend/app/config.py`).
- Tests in `backend/tests/` using `pytest` + `pytest-asyncio`.
- Raise typed exceptions; let FastAPI's exception handlers convert. Don't swallow.

**TypeScript (frontend):**
- Next.js 14 App Router.
- **No `any` types.** Anywhere. If TypeScript complains, fix the type, don't escape it.
- Tailwind for styling. shadcn-style components in `frontend/src/components/`.
- SSE for live progress (`frontend/src/hooks/useSSE.ts`).

**Git:**
- Small, frequent commits.
- Conventional-commit prefixes: `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`.

## Running locally

```bash
git clone <your fork>
cd <repo>

# 1. Bring up Postgres + Redis
docker compose up -d

# 2. Backend (terminal 1)
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: paste at minimum SERPER_API_KEY, GEMINI_API_KEY, SCRAPE_DO_API_KEY
uvicorn app.main:app --reload &
arq app.workers.pipeline.WorkerSettings &

# 3. Frontend (terminal 2)
cd ../frontend
npm install
cp .env.example .env.local
npm run dev
```

Open http://localhost:3000 — the tool grid loads.

## Deployment

The reference stack used by quickenrich.io is Railway (backend + Redis) +
Vercel (frontend) + Supabase (Postgres) + Resend (email). Full step-by-step
instructions: [`docs/hosting.md`](docs/hosting.md). Alternatives (Fly,
Render, Neon, Postmark, etc.): [`docs/swapping-providers.md`](docs/swapping-providers.md).

## Common tasks for an agent

**Add a new tool**
1. Create `frontend/src/app/tools/<slug>/page.tsx` (copy an existing tool as a starting point).
2. Create `frontend/src/app/tools/<slug>/README.md`.
3. Register in `frontend/src/lib/tool-registry.ts` (`tools` array).
4. Add `backend/app/routers/<name>.py` and wire it into `backend/app/main.py`.
5. If the tool has a Phase 0 (discovery), add `backend/app/workers/<name>_pipeline.py`; otherwise reuse `pipeline.py` or `intel_pipeline.py`.
6. If the tool needs new services, add files under `backend/app/services/`.
7. Add a homepage card if appropriate (`frontend/src/app/page.tsx` already iterates the registry).

**Add a new LLM provider**
1. Create `backend/app/services/llm/<provider>.py` implementing the interface in `base.py`.
2. Update the factory in `backend/app/services/llm/__init__.py` — add a new `if settings.llm_provider == "<provider>": ...` clause.
3. Add the corresponding `<PROVIDER>_API_KEY` to `backend/.env.example`.
4. Add the SDK to `backend/requirements.txt`.

**Change the email template**
- `backend/app/services/email_service.py` (template rendering and Resend send call).
- `backend/app/services/delivery.py` (the caller — composes email body from job results).

**Swap a provider entirely**
- See [`docs/swapping-providers.md`](docs/swapping-providers.md). Tier 1 (DB, backend host) gets full playbooks; Tier 2 (scraping, LLM) gets recipes; Tier 3 (email, frontend host, search, redis) gets pointers.

## Pitfalls

- **`JWT_SECRET=change-me-in-production`** in dev is fine, but rotate to a real random string before deploying. Generate with `openssl rand -hex 32`.
- **Without `SCRAPE_DO_API_KEY`**, scraping falls back to plain HTTPS and many sites block — expect ~10 results per G2 category instead of ~80+. Same applies to general site crawling.
- **Funding-intel `/discover` endpoint** is intentionally restricted to `hours=24|48` (`backend/app/routers/funding.py`). Don't widen without considering cost — it's hot-cached for 1h to prevent abuse.
- **CORS allowlist** lives at `backend/app/main.py:46` (`allow_origins=[...]`). When you change the frontend domain, update that list or you'll get blocked browser requests.
- **UTF-8** is forced on QuickEnrich responses — don't strip that handling (added in commit `40d8b52`).

## Where things are written down

- **Specs** — `docs/superpowers/specs/`
- **Plans** — `docs/superpowers/plans/`
- **Hosting playbook** — [`docs/hosting.md`](docs/hosting.md)
- **Provider-swap playbook** — [`docs/swapping-providers.md`](docs/swapping-providers.md)
- **Per-tool README** — `frontend/src/app/tools/<slug>/README.md`
