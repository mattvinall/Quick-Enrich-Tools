# QuickEnrich Tools

A free, open-source suite of 6 lead-enrichment tools you can clone, run on
your own laptop with your own API keys, customize with your favorite AI
coding agent, and (optionally) self-host for your team.

**Live demo:** https://quick-enrich-tools.vercel.app

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
git clone https://github.com/mattvinall/Quick-Enrich-Tools.git
cd quickenrich-tools

# 1. Local Postgres + Redis
docker compose up -d

# 2. Backend (terminal 1)
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
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
| [QuickEnrich](https://app.quickenrich.io/promo) | for contact enrichment | **50,000 free credits** with the link |
| [Resend](https://resend.com) | usually skip self-hosted | only matters if you want CSVs emailed |
| Postgres + Redis | yes | free via `docker compose` |

> **Tip:** QuickEnrich is offering 50K free credits to new accounts via [app.quickenrich.io/promo](https://app.quickenrich.io/promo). That covers the contact-enrichment side of the pipeline for a long time at zero cost.

## Hosted vs. self-hosted (where API keys live)

The same codebase supports two deployment modes. The split below is the one you'll likely follow when self-hosting:

| Mode | What lives in `backend/.env` | What the user types into the UI |
|---|---|---|
| Hosted (the public site) | Only `GEMINI_API_KEY` + `RESEND_API_KEY` | All three: `serper`, `scrape_do`, `quickenrich` per-job |
| **Self-hosted (you)** | All your keys: Gemini, Serper, Scrape.do, QuickEnrich, Resend (optional) | Nothing — the backend falls back to `.env` |

So when you clone, you populate `backend/.env` once and forget it. The UI config fields can stay empty; the worker uses your `.env` values via `effective_key = user_provided_key or settings.<key>`.

## Want to host it for your team?

The reference stack is Railway + Vercel + Supabase + Resend (~$10–20/mo for
a small team). See [`docs/hosting.md`](docs/hosting.md) for full deployment
instructions, plus alternatives (Fly, Render, Neon, Firebase, etc.).

## Customizing for your stack

This repo is designed to be forked and customized. Use any AI coding agent
(Claude Code, Codex, Cursor, Aider) to swap providers — Supabase for Neon,
Railway for Fly, Scrape.do for SpiderCloud, whatever.

See [`docs/swapping-providers.md`](docs/swapping-providers.md) for tiered
playbooks. Each section ends with a copy-paste prompt you can hand to your
agent.

## Open it in your agent

```bash
# Claude Code
claude

# Codex CLI
codex

# Cursor
cursor .
```

All three read [`AGENTS.md`](./AGENTS.md), which is the single source of
truth for architecture, conventions, and where everything lives.

## Architecture (one paragraph)

Next.js frontend (Vercel-friendly) talks to a FastAPI backend (Python 3.11)
which dispatches jobs to ARQ workers backed by Redis. Each tool runs a
multi-phase pipeline (Discover → Resolve → Crawl → Extract → Enrich →
Deliver) calling external services (Serper, Scrape.do, LLM, QuickEnrich)
and storing results in Postgres. CSVs are emailed via Resend or downloaded
directly.

For the full architecture deep-dive, read [`AGENTS.md`](./AGENTS.md).

## Contributing

Issues and PRs welcome. Please read [`AGENTS.md`](./AGENTS.md) before
opening a PR — it's also a great human onboarding doc.

## License

MIT — see [`LICENSE`](./LICENSE).

## Credits

Built by [QuickEnrich](https://quickenrich.io). The hosted version of these
tools (free) lives at https://quick-enrich-tools.vercel.app.
