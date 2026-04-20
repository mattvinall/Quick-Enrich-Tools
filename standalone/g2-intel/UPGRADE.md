# UPGRADE — Turn this into a team app

The standalone script runs on one laptop, one user. If you want a shared tool with a web UI, saved job history, and multi-user access, here's the path.

## What the hosted version adds

| Feature | Standalone | Hosted |
|---|---|---|
| UI | CLI | Web app |
| Job queue | Synchronous — blocks your terminal | Async — submit and close the tab |
| History | Whatever CSVs you saved | Stored in Supabase, searchable |
| Multi-user | One .env, one user | Auth, per-user API keys |
| Progress streaming | tqdm bar | Server-Sent Events to the browser |
| Caching | None (re-burns credits) | Redis, 7-day TTL — 10× cost reduction on repeat queries |
| Delivery | CSV on disk | Email with link, download expires after N days |

## Stack

- **[Supabase](https://supabase.com)** — Postgres database + auth. Free tier covers ~50k rows.
- **[Railway](https://railway.app)** — hosts the Python backend + Redis + ARQ job worker. ~$10/mo entry.
- **[Vercel](https://vercel.com)** — hosts the Next.js frontend. Free tier is plenty.
- **[Resend](https://resend.com)** — transactional email for delivering CSV links. Free tier ~3k emails/mo.

**Ballpark cost:** $20–40/mo for a team of 5 doing a few hundred enrichments per day.

## The 6-step migration

### 1. Database — Supabase

Create a project at [supabase.com](https://supabase.com). In the SQL editor, create these tables:

```sql
create table jobs (
  id uuid primary key default gen_random_uuid(),
  user_email text not null,
  status text not null default 'pending',          -- pending|running|completed|failed
  config jsonb not null,                           -- {categories, max, contacts, titles}
  created_at timestamptz default now(),
  completed_at timestamptz
);

create table job_results (
  id bigserial primary key,
  job_id uuid references jobs(id) on delete cascade,
  row_index int,
  data jsonb not null,                             -- same shape as a CSV row
  created_at timestamptz default now()
);

create index on jobs (user_email, created_at desc);
create index on job_results (job_id);
```

Copy your Supabase URL and anon key. You'll need them on the backend.

### 2. Job queue — Redis + ARQ

[ARQ](https://arq-docs.helpmanual.io/) is a lightweight Redis-backed queue. On Railway, add a Redis service (one click) and a Python service. The Python service runs both the API and the worker.

### 3. Wrap the CLI into an API

Take `run.py` and restructure as a FastAPI app:

```python
# api.py
from fastapi import FastAPI
from arq import create_pool
app = FastAPI()

@app.post("/jobs")
async def submit(body: dict):
    redis = await create_pool(...)
    job = await redis.enqueue_job("run_enrichment", body)
    # Also persist to Supabase jobs table
    return {"job_id": job.job_id}
```

Turn the `_process_one` function into an ARQ task that writes each result row to Supabase's `job_results` as it finishes.

### 4. Frontend — Next.js

Build a page with a form (the CLI flags become form fields), a submit button, and a table of past jobs. Poll `/jobs/{id}` or use SSE for live progress.

QuickEnrich already has this built. If you want to white-label it, fork the `frontend/` directory of the original repo — the G2CategorySelector component works out of the box.

### 5. Auth

Supabase Auth gives you email/password, magic links, and OAuth out of the box. Gate the job submission endpoint with:

```python
user = await supabase.auth.get_user(request.headers["authorization"])
if not user:
    raise HTTPException(401)
```

### 6. Deploy

- Frontend: `vercel --prod`
- Backend: push to GitHub, Railway auto-deploys. Set env vars in Railway dashboard (same names as your `.env` + Supabase/Redis URLs).
- Point a custom domain at Vercel. Done.

## When is the upgrade worth it?

- **Running >100 jobs/week** — Redis caching pays for itself in Scrape.do credits saved
- **Multiple team members need access** — hosted auth beats sharing a .env file
- **You want to sell this to others** — the hosted version is the monetizable product

## When to stick with standalone

- **You're the only user** — save yourself the ops overhead
- **Compliance requirements** — local-only means your prospect data never leaves your machine
- **Experimenting** — don't provision infrastructure for something you might not use twice

## Getting help

The QuickEnrich team (https://quickenrich.io) can take you from standalone to hosted in a day for a consulting fee. Or you can use this doc as a spec and have any competent Python/Next.js dev build it.
