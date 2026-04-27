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

**Why this is straightforward:** the code only depends on Postgres-compatible
SQL via SQLAlchemy. Supabase is just a Postgres host; Neon, RDS, Cloud SQL,
self-hosted, or your local docker-compose Postgres all work identically.

**Files to touch:**
- `backend/.env` → swap `DATABASE_URL` to your new Postgres connection string. SQLAlchemy needs the `postgresql+asyncpg://` scheme — replace `postgresql://` with `postgresql+asyncpg://` if your provider hands you the plain form.
- `database/schema.sql` → run this once on your new DB. Use `psql "$DATABASE_URL" < database/schema.sql` or your provider's SQL editor.
- `backend/app/database.py` → no change needed for vanilla Postgres. If your provider needs SSL or specific pool args, they go in `create_async_engine(...)` (line 11).

**Auth note:** if you were using Supabase Auth, Neon doesn't bundle auth —
pick Auth0, Clerk, or roll your own JWT. The backend already has a JWT
helper at `backend/app/auth.py`.

**Test:**
1. `docker compose down` (stop local Postgres if running)
2. Update `.env` with new `DATABASE_URL`
3. `cd backend && uvicorn app.main:app --reload`
4. Submit a small job through the UI; confirm it persists (`SELECT * FROM jobs LIMIT 5`).

**Agent prompt:**
> Swap Postgres host from Supabase to Neon. The seam is `DATABASE_URL` in
> `backend/.env`. Run `database/schema.sql` against the new database.
> Verify by submitting a small job and confirming a row lands in the `jobs`
> table.

### Database: Supabase → Firebase (Firestore)

**Honest warning:** Firebase Firestore is document-oriented. The current
schema uses joins (`jobs` ↔ `job_results`). A direct port means rewriting
`backend/app/database.py` and every query against `models.py`. This is a
real refactor, not a config change.

**If you still want it:**
- Replace SQLAlchemy with the Firebase Admin SDK in `backend/app/database.py`.
- Convert `models.py` from SQLAlchemy ORM to Firestore document classes.
- Each query in routers and workers needs rewriting (`session.execute(select(...))` → `firestore_client.collection(...).where(...)`).
- ARQ stays the same — Redis is independent.

**Recommendation:** unless you're already a Firebase shop, stay on Postgres
(Neon is free).

**Agent prompt:**
> I want to migrate this codebase from Postgres to Firebase Firestore. Read
> `backend/app/database.py`, `backend/app/models.py`, and every router and
> worker file. Plan the rewrite — produce a list of every file you'd touch
> and a rough line-count estimate before any code changes.

### Backend hosting: Railway → Fly.io / Render / self-hosted Docker

**Files relevant to deploy:** `backend/Procfile`, `backend/requirements.txt`,
`backend/runtime.txt`, repo root for any new `Dockerfile`.

**Fly.io.** Add a `backend/Dockerfile` (FROM python:3.11-slim, COPY,
pip install, CMD uvicorn). Add `backend/fly.toml`:

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

**Render.** Add a `render.yaml` at repo root with two services (web +
worker) sharing env. Render auto-provisions Postgres + Redis if you want to
colocate; otherwise point at Supabase + Upstash.

**Self-hosted Docker.** Write a `Dockerfile` (same as Fly's) plus a
`compose.prod.yml` that adds the backend service to the existing
`docker-compose.yml`. Front it with Caddy or Nginx for TLS.

**Agent prompt:**
> Switch backend hosting from Railway to Fly.io. Read `backend/Procfile`
> and `backend/requirements.txt`. Create `backend/Dockerfile` and
> `backend/fly.toml` with web + worker processes. Document the
> `fly secrets set` commands needed. Do not delete Railway-specific files
> (`Procfile`, `railway.toml`) — leave them for users who stay on Railway.

---

## Tier 2: Single-file swaps

### Scraping: Scrape.do → SpiderCloud / Apify / Bright Data

**Single seam:** `backend/app/services/scraper.py`. The current
implementation builds a Scrape.do URL like:

```
https://api.scrape.do/?token={SCRAPE_DO_API_KEY}&url={target_url}&render=false
```

**SpiderCloud equivalent:** their proxy endpoint format is documented at
https://spider.cloud/docs/api. Replace the URL builder. Keep the
`httpx.AsyncClient` and retry/timeout machinery.

**Apify equivalent:** different model — you call an actor and poll for
results. Wrap that polling in the same async function signature
`async def fetch(url) -> str` so the rest of the pipeline doesn't change.

**Bright Data equivalent:** they offer a proxy you set as the `httpx`
proxy URL. Lighter swap: point `httpx.AsyncClient(proxies=...)` at Bright
Data's URL and drop the Scrape.do URL building entirely.

**Test:** run G2 Intel against a small category (e.g. `product-analytics`,
max 5); confirm 5 product pages scrape successfully.

**Agent prompt:**
> Swap the scraping provider in `backend/app/services/scraper.py` from
> Scrape.do to <SpiderCloud | Apify | Bright Data>. Preserve the
> `async def fetch(url) -> str` signature so callers don't change. Update
> `backend/.env.example` to swap `SCRAPE_DO_API_KEY` for the new provider's
> env. Add a 1-line comment at the top of `scraper.py` saying which
> provider this build uses.

### LLM: Gemini ↔ OpenAI ↔ Anthropic

**Already abstracted:** `backend/app/services/llm/base.py` defines the
interface; `gemini.py` and `openai_provider.py` implement it. The provider
is selected at runtime by `LLM_PROVIDER` env. Factory:
`backend/app/services/llm/__init__.py` (`get_llm_provider`).

**Adding Anthropic:**
1. Create `backend/app/services/llm/anthropic_provider.py` — implement the
   same interface as `gemini.py`.
2. Update the factory in `backend/app/services/llm/__init__.py`:
   ```python
   if settings.llm_provider == "anthropic":
       from app.services.llm.anthropic_provider import AnthropicProvider
       return AnthropicProvider()
   ```
3. Add `ANTHROPIC_API_KEY=` to `backend/.env.example`.
4. Add `anthropic==0.x` to `backend/requirements.txt`.

**Test:** `LLM_PROVIDER=anthropic` in `.env`, restart backend, submit a
Company Intel job, confirm extraction completes.

**Agent prompt:**
> Add Anthropic Claude as a third LLM provider in
> `backend/app/services/llm/`. Mirror the structure of `gemini.py` and
> `openai_provider.py`. Update the factory in `__init__.py`. Add the env
> var and the SDK to `requirements.txt`. End with a smoke test plan.

---

## Tier 3: Drop-in swaps

### Email: Resend → Postmark / SendGrid

Single seam: `backend/app/services/email_service.py`. Replace the Resend
SDK call with the new provider's SDK. Update env var name. ~10 lines of
code change.

### Frontend hosting: Vercel → Netlify / Cloudflare Pages

Next.js 14 deploys cleanly to both. For Netlify, install
`@netlify/plugin-nextjs` and add a `netlify.toml`. For Cloudflare, use
`@cloudflare/next-on-pages`. Env vars move with you.

### Search: Serper → SerpApi / Google Custom Search

Single seam: `backend/app/services/serper.py`. URL pattern + auth header
changes. Output schema matches between Serper and SerpApi closely.

### Redis: Railway Redis → Upstash / self-hosted

`REDIS_URL` env change only. Upstash provides a Redis-compatible URL. ARQ
doesn't care about the host.

---

## Common pitfalls

- **Forgetting the worker process.** Some swaps (especially Railway → other)
  lose the ARQ worker if you only deploy the web process. Symptom: jobs
  queue up but never run. The web process and the worker are separate.
- **CORS.** Changing the frontend domain means updating the CORS allowlist
  in `backend/app/main.py` (`allow_origins=[...]`).
- **Email sending domain.** Switching email providers requires re-verifying
  your sending domain. Plan for SPF/DKIM DNS propagation.
- **Schema drift.** If you swap databases, the schema must be applied to
  the new DB before the backend will boot.
