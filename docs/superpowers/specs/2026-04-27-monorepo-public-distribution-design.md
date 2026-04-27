# Public-Distribution Design — QuickEnrich Tool Suite

**Date:** 2026-04-27
**Status:** Design (awaiting user sign-off → writing-plans)
**Owner:** Matt Vinall

## Goal

Make the QuickEnrich monorepo cloneable from GitHub so any developer can fork it, run it locally on their own laptop with their own API keys, and (optionally) deploy a hosted version to their own infrastructure with whatever providers they prefer (Supabase ↔ Neon, Railway ↔ Fly, Scrape.do ↔ SpiderCloud, etc.).

**Local-first framing.** The primary and easiest path is "clone, set `.env`, `npm run dev` + `uvicorn`, done." No Railway, no Vercel, no Resend required for someone who just wants to run the tools themselves. Hosted/team deployments are an opt-in second path documented separately.

The customization layer is the user's coding agent (Claude Code, Codex, Cursor) — not runtime abstractions in the codebase.

## Cost Isolation (For Matt)

Every fork is fully independent. When someone clones the public repo, they bring their own Supabase project, own Railway account (if any), own Serper / Gemini / Scrape.do / Resend / QuickEnrich keys. Matt's accounts are never touched. The only way Matt would get billed is if real credentials for his infrastructure leaked into the repo — eliminated by the pre-flight key rotation + history scrub.

## Non-Goals

- No runtime adapter/plugin/abstraction layer for swapping providers. Agents do swaps with good docs; pluggability in the code itself is the over-engineering trap.
- No per-tool CLI extractions. The existing `standalone/g2-intel/` is from a different bet and gets deleted.
- No template repos, "Use this template" automation, or scaffolding generators. Just `git clone`.
- No new packages, monorepo splits, or workspace restructuring. The current shape is fine.

## Three Readers We're Optimizing For

1. **An AI coding agent** (Claude Code, Codex, Cursor, Aider) running `git clone <repo> && cd <repo>` after the user invokes it. Must understand architecture, conventions, and provider seams in one read.
2. **A developer skimming the README** deciding whether to clone.
3. **The GitHub repo page** (description, topics, license badge, social preview) as first impression.

## Pre-Flight (Blockers Before Public Flip)

Discovered during brainstorm — must complete before flipping repo public:

1. **Rotate 4 leaked keys** committed in `95a479b` (2026-03-16):
   - Serper, Gemini, OpenAI, QuickEnrich
   - Scrape.do and Resend keys are NOT in history.
   - Update Railway secrets + local `.env` after rotation.
2. **Scrub history with `git filter-repo`** to remove the leaked-key blob. Decision: scrub (not just rotate-and-leave). Repo is going to a public audience that will judge it on first impression; rotated-dead keys still look unprofessional and trip key-scanning bots.
3. **Verify clean** with a final secrets sweep after scrub.
4. **Force-push the rewritten history** to origin. This is destructive but acceptable — the only existing clone is Matt's local working copy.

## Deliverables

### 1. `AGENTS.md` (root, primary doc)

Cross-agent standard. ~300–500 lines. Sections:

- **What this is** — 6-tool lead enrichment suite, 1-paragraph product overview.
- **Architecture at a glance** — monorepo layout (`backend/`, `frontend/`, `database/`, `docs/`), what each contains, request flow (frontend → FastAPI → ARQ worker → external services → Supabase → Resend delivery).
- **The 6 tools and their files** — for each tool: description, frontend route (`frontend/src/app/tools/<slug>/`), backend router (`backend/app/routers/<name>.py`), services it touches.
- **Pipeline pattern** — Phase 0 (discovery) → Resolve → Crawl → Extract → Enrich → Deliver. Where each phase lives in code.
- **External services and their seams** — table mapping each provider to the file(s) that call it. This is the swap-target index.
- **Conventions** — Python style, TypeScript style, no `any` types, async patterns, error handling, where tests live.
- **How to set up locally** — clone, env vars, `pip install`, `npm install`, run.
- **How to deploy** — pointer to `docs/hosting.md` for the reference stack (Railway + Vercel + Supabase + Resend) and `docs/swapping-providers.md` for alternatives.
- **How to swap providers** — pointer to `docs/swapping-providers.md` with one-paragraph TL;DR.
- **Common tasks** — "add a new tool," "add a new LLM provider," "change the email template."

### 2. `CLAUDE.md` (root, one-line stub)

```
This project uses AGENTS.md as the single source of truth for agent guidance. See ./AGENTS.md.
```

Avoids drift; Claude Code in 2026 reads `AGENTS.md` fine.

### 3. `README.md` (root, human-facing)

~180 lines. Sections, in this order:

- One-line pitch + screenshot/GIF of the live tools.
- Live demo link → quick-enrich-tools.vercel.app.
- "What's included" — the 6 tools, one bullet each.
- **"Run it locally in 5 minutes" (the primary path)** — clone, copy `.env.example` → `.env`, paste your Serper + Gemini + Scrape.do keys, `docker compose up redis postgres`, `uvicorn`, `npm run dev`. The README leads with this because most readers want this, not a hosted deployment.
- "What it costs (running it yourself)" — short table: Serper free tier, Gemini free tier, Scrape.do $29/mo entry, Postgres free, Redis free. Calibrates expectations.
- **"Want to host it for your team?"** — one paragraph + pointer to `docs/hosting.md` (Railway+Vercel+Supabase+Resend, plus alternatives via the swap playbook).
- "Customizing for your stack" — one paragraph + link to `docs/swapping-providers.md`.
- "Open it in your agent" — copy-paste invocation snippets for Claude Code, Codex, Cursor.
- License badge, contributing pointer, credits to QuickEnrich.

### 4. Per-tool `README.md`

One file per tool at `frontend/src/app/tools/<slug>/README.md`. ~30–60 lines each. Sections:

- What the tool does (1 paragraph).
- User flow (3–5 bullets).
- Backend routes hit.
- Services used (Serper, Scrape.do, etc.).
- Key files (frontend page, backend router, relevant service modules).
- Notable design decisions (e.g., "P3 takes user-provided keys for Serper and QuickEnrich; backend pays for Scrape.do and LLM").

Seven tools × ~50 lines = ~350 lines total. Worth it because it's the first thing an agent reads when asked "modify the funding-intel tool."

### 5a. `docs/hosting.md` (new — opt-in path)

For users who want a deployed/team version. ~200 lines. Covers:

- The reference stack (what QuickEnrich.io itself uses): Railway (backend + Redis) + Vercel (frontend) + Supabase (Postgres + storage) + Resend (email). Estimated cost for a small team.
- Step-by-step deploy of the reference stack from a fresh fork.
- Pointer to `swapping-providers.md` for "I want to use X instead of Y."
- Local mode vs. hosted mode comparison table (when to upgrade).

This file is intentionally **separate** from `README.md` so the README stays focused on the local-first primary path.

### 5b. `docs/swapping-providers.md`

The provider-swap playbook. **Tiered by effort**, not equal-weight prose for every provider.

**Tier 1 — Full playbook** (the swaps users actually want, biggest blast radius):
- **Database: Supabase → Neon / Postgres anywhere** — schema is `database/schema.sql`, connection in `backend/app/database.py`, env var is `DATABASE_URL`. Auth migration notes (Supabase Auth → Auth0/Clerk/none).
- **Database: Supabase → Firebase** — bigger lift; Firestore is document-oriented. Concrete pointers + warning that schema-driven joins won't carry over directly.
- **Backend hosting: Railway → Fly.io / Render / self-hosted Docker** — `Procfile`, `railway.toml`, `requirements.txt`, ARQ worker startup. Concrete swap recipe per target.

**Tier 2 — Mid playbook** (moderate effort):
- **Scraping: Scrape.do → SpiderCloud / Apify / Bright Data** — single seam at `backend/app/services/scraper.py`. Show the URL pattern + auth header for each alternative.
- **LLM: Gemini ↔ OpenAI ↔ Anthropic** — already abstracted at `backend/app/services/llm/`. Adding a new provider means dropping a file in that directory + flipping `LLM_PROVIDER`. Show the existing `base.py` interface.

**Tier 3 — Light pointers** (drop-in, near zero work):
- Email: Resend → Postmark / SendGrid (single env + ~10-line service swap).
- Frontend host: Vercel → Netlify / Cloudflare Pages.
- Search: Serper → SerpApi / Google CSE.
- Redis provider: Railway Redis → Upstash / self-hosted.

Each tier-1 swap gets ~150 lines (overview, files to touch, env changes, gotchas, test steps). Tier 2 gets ~50 lines each. Tier 3 gets a one-paragraph pointer.

**Format convention:** every swap section ends with a copy-paste prompt the user can hand to their agent: *"Swap Supabase for Neon. The seams are X, Y, Z. Update env vars A, B. Confirm by running test C."*

### 5c. `docker-compose.yml` (new, root)

A minimal compose file that brings up local Postgres + Redis with one command. Removes "install Postgres and Redis on your machine" friction for the local-first path. Backend and frontend stay outside compose (they're ergonomic to run with `uvicorn` / `npm run dev` directly).

### 5d. `backend/.env.example` and `frontend/.env.example` review

Audit both `.env.example` files. Ensure:
- Every var has a comment explaining what it's for.
- Local-mode-required vars are marked `# REQUIRED for local`.
- Hosted-mode-only vars are marked `# OPTIONAL (only needed when deploying)`.
- All values are placeholders only, never real keys.

### 6. `LICENSE`

MIT. Standard text, copyright "Synapse LLC / QuickEnrich" (or whatever Tom prefers — note for Matt to confirm).

### 7. Landing-page CTA

Minimal. Two additions to quick-enrich-tools.vercel.app:

- **Top nav:** GitHub icon → repo URL.
- **One section near the bottom of the homepage:** "Open source. Clone it." — three sentences + the `git clone` command + a "Get the source on GitHub" button.

No redesign. Just a section component drop-in.

### 8. Delete `standalone/g2-intel/`

Single commit removes the directory. Git history preserves it forever if anyone ever wants it back. Rationale: half-orphaned artifact from a different distribution bet (CLI for laptop users) — confuses readers of the new monorepo-public narrative.

### 9. GitHub repo metadata

- **Description:** "Open-source lead enrichment tool suite — 6 free tools you can clone, customize, and self-host."
- **Topics:** `lead-enrichment`, `nextjs`, `fastapi`, `claude-code`, `agents-md`, `supabase`, `web-scraping`, `b2b`.
- **Social preview image:** screenshot of the tool grid from quick-enrich-tools.vercel.app.
- **Pin issue:** "Welcome — start with `AGENTS.md`."

## Architecture

No code architecture changes. The deliverable is documentation + cleanup. The existing monorepo shape (`backend/` FastAPI + ARQ, `frontend/` Next.js, `database/` schema, `docs/`) is what users will fork.

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Leaked keys in history go public | Pre-flight rotation + history scrub gates the public flip. |
| Docs drift from code over time | AGENTS.md is the single source of truth; per-tool READMEs are colocated with the tool code so they're touched together. |
| User attempts a swap, breaks their fork, blames the upstream | Each swap section ends with a verification recipe. README is explicit that this is "fork and own it" not "managed product." |
| Tom or Matt rotates keys but forgets to update Railway | Rotation task explicitly includes Railway env update + smoke-test step. |
| Future tools get added without per-tool README | Add a contributor checklist to AGENTS.md: "new tool = new README." |

## Out of Scope (Explicitly Rejected)

- Provider abstraction libraries / dependency injection refactor.
- Per-tool standalone CLIs (deleting the one that exists).
- A web UI for "configure your stack and download a customized zip."
- Multi-tenant SaaS-ification.
- A "QuickEnrich Cloud" managed offering. (Tom can build that separately if he wants; it's not part of the open-source ship.)
- CI/CD examples for every deploy target. AGENTS.md mentions the current Railway+Vercel setup; alternatives go in the swap playbook only.

## Order of Operations

1. **User-blocking pre-flight** (Matt + Tom): rotate the 4 keys, update Railway, smoke-test. *In progress.*
2. Delete `standalone/g2-intel/`.
3. Add root `docker-compose.yml` for local Postgres + Redis (so the README's local-mode commands actually work).
4. Audit and annotate `backend/.env.example` and `frontend/.env.example`.
5. Write `AGENTS.md`.
6. Write `CLAUDE.md` stub.
7. Write root `README.md` (local-first framing).
8. Write per-tool READMEs (×7).
9. Write `docs/hosting.md`.
10. Write `docs/swapping-providers.md`.
11. Add `LICENSE` (MIT).
12. Run `git filter-repo` to scrub leaked-key blob from history.
13. Final secrets sweep (verify clean).
14. Add landing-page GitHub CTA on Vercel frontend (separate small change).
15. Push (force-with-lease, since history rewrote) to origin.
16. Flip repo public on GitHub. Set description + topics + social preview.
17. Manual smoke test: clone the public repo into a clean directory, follow the README's local-mode instructions verbatim, ensure dev server runs end-to-end.

## Success Criteria

- A developer with no prior context can clone the public repo, open it in any agent, and within 30 minutes have the dev server running locally.
- The user's stated swap examples (Supabase → Neon, Scrape.do → SpiderCloud, Railway → Fly) each have a concrete playbook in `docs/swapping-providers.md`.
- No real keys exist in any commit on `main` after history scrub.
- Public repo has license, description, topics, and pinned welcome issue.
