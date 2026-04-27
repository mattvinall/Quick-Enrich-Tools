# Hosting QuickEnrich for a Team

The local-first instructions in [`README.md`](../README.md) are enough for
one user on one laptop. If you want a deployed version your team can hit
from a URL, this is the playbook.

## Reference stack

This is what quickenrich.io itself runs on:

| Layer | Service | Cost |
|---|---|---|
| Backend (FastAPI + ARQ worker) | [Railway](https://railway.app) | ~$10/mo |
| Frontend (Next.js) | [Vercel](https://vercel.com) | free |
| Postgres | [Supabase](https://supabase.com) | free for small teams |
| Redis (queue + cache) | Railway Redis add-on | included with Railway |
| Email (CSV delivery) | [Resend](https://resend.com) | free 3k/mo |

**Total: ~$10–20/mo.** A small team running a few hundred enrichments/day
fits in this budget. Want a different stack? See
[`swapping-providers.md`](swapping-providers.md).

## Step-by-step deploy (reference stack)

### 1. Postgres on Supabase

1. Sign up at [supabase.com](https://supabase.com), create a project.
2. Open the SQL editor, paste the contents of `database/schema.sql`, run.
3. Settings → Database → copy the **connection string**. Use the direct
   `postgresql://` URL for Railway, then convert to `postgresql+asyncpg://`
   for SQLAlchemy by replacing the scheme. You'll set this as `DATABASE_URL`.
4. (Optional) Enable Row-Level Security in Authentication → Policies if you
   plan to use Supabase Auth.

### 2. Redis on Railway (with the backend)

1. Sign up at [railway.app](https://railway.app).
2. New Project → Deploy from GitHub Repo → pick your fork.
3. Railway will auto-detect Python and run `Procfile`. Add a Redis service
   from the New → Database → Redis menu.
4. Railway auto-provisions `REDIS_URL` to your service.

### 3. Backend on Railway

In the Railway dashboard, add these env vars (Variables tab):

```
DATABASE_URL=<from Supabase, with postgresql+asyncpg:// scheme>
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

**Important: the ARQ worker is a separate process.** Railway's `Procfile`
only runs `web` by default. The worker won't start unless you do one of:

- Add a second Railway service pointing at the same repo with the start
  command `arq app.workers.pipeline.WorkerSettings`, **OR**
- Edit `Procfile` to use a process manager like `honcho` or `tmuxp` to run
  both — fiddly; the second-service approach is cleaner.

Without the worker, jobs queue up in Redis and never run. Symptom: progress
bar in the UI stays at 0%.

### 4. Frontend on Vercel

1. `vercel --prod` from the `frontend/` directory, **OR** import the GitHub
   repo from the Vercel dashboard with **Root Directory** set to `frontend`.
2. Vercel env: `NEXT_PUBLIC_API_URL=<your Railway backend URL>`.
3. Update CORS allowlist in `backend/app/main.py` (`allow_origins=[...]`)
   to include your Vercel domain. Redeploy backend.
4. (Optional) Point a custom domain at Vercel.

### 5. Email on Resend

1. Sign up at [resend.com](https://resend.com), verify a sending domain.
2. Generate an API key, paste into Railway as `RESEND_API_KEY`.
3. Update the `from:` address in `backend/app/services/email_service.py` if
   it doesn't match your verified domain.

### 6. Smoke test the deploy

Submit a CSV to **Company Location Finder** (the simplest pipeline). Watch
the SSE progress in the UI. Confirm the email arrives. Confirm the CSV
downloads.

## Local mode vs. hosted mode

| Need | Local | Hosted |
|---|---|---|
| One user, occasional runs | ✅ | overkill |
| Team-wide access | ❌ | ✅ |
| Long-running jobs (close laptop) | ❌ | ✅ |
| Email delivery of CSVs | possible | natural |
| Auth / per-user history | manual | natural |

A reasonable path: start local. When you find yourself running it daily or
a teammate asks for access, deploy.

## Want a different stack?

[`swapping-providers.md`](swapping-providers.md) has playbooks for:
- Database: Supabase → Neon, Postgres anywhere, Firebase
- Backend hosting: Railway → Fly.io, Render, self-hosted Docker
- Scraping: Scrape.do → SpiderCloud, Apify, Bright Data
- LLM: Gemini ↔ OpenAI ↔ Anthropic
- Email: Resend → Postmark, SendGrid
- Frontend: Vercel → Netlify, Cloudflare Pages
