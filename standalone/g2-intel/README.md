# QuickEnrich G2 Intel — Standalone

Discover companies listed in G2 software categories, scrape their websites, and extract structured business intelligence. Outputs a CSV. No database, no cloud account — runs on your laptop.

## Quick start (2 minutes)

```bash
# 1. Install
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Open .env and paste your API keys (SERPER_API_KEY and GEMINI_API_KEY required)

# 3. Run
python run.py --categories product-analytics --max 25 --output results.csv
```

When it finishes, open `results.csv` in Excel, Google Sheets, or anywhere.

## What you need

| Service | Required? | Why | Cost |
|---|---|---|---|
| [Serper](https://serper.dev) | Yes | Google search for company domains | ~$50/mo for 50k searches |
| [Gemini](https://ai.google.dev) | Yes (or OpenAI) | LLM extraction of intel from scraped pages | Free tier works for small runs |
| [Scrape.do](https://scrape.do) | Strongly recommended | Bypasses G2's anti-bot — without it, ~10 products per category max | $29/mo entry tier |
| [QuickEnrich](https://quickenrich.io) | Optional | Named contacts (email, LinkedIn) | Per-request pricing |

## CLI options

```
python run.py --help

  --categories  TEXT   Comma-separated G2 slugs (required)
  --max         INT    Max products per category (default 25)
  --output      PATH   Output CSV (default results.csv)
  --concurrency INT    Concurrent companies (default 4)
  --contacts    INT    Named contacts per company (default 0, requires QUICKENRICH_API_KEY)
  --titles      TEXT   Titles to search for (default "CEO,Founder,Co-Founder")
```

## List available categories

```bash
python -c "from intel.categories import G2_CATEGORIES; [print(f'{c[\"slug\"]:40} {c[\"name\"]}') for c in G2_CATEGORIES]"
```

## Output columns

`company_name, g2_url, g2_category, domain, industry, niche, description, target_market, address, phone, case_studies, website_contacts, contact_first_name, contact_last_name, contact_title, contact_email, contact_phone, contact_linkedin`

## Troubleshooting

**"Only getting ~10 products per category"** — You don't have `SCRAPE_DO_API_KEY` set. G2 blocks direct scraping, so the script falls back to Google search which caps at ~10 indexed product pages per query. Add scrape.do to unlock the full 80+ per category.

**"Empty intel rows"** — The domain might be a content site (blog, directory) rather than a product homepage. Check the `domain` column; if it looks wrong, the Serper resolve picked a bad top result.

**Runs slowly** — 25 companies × (3 pages × scrape + 1 LLM call) = ~15 min at concurrency=4. Bump `--concurrency` up to 8 if you're not rate-limited.

## Next steps

- **SOP.md** — detailed playbook for daily use, cost math, scaling to hundreds of companies, best categories.
- **UPGRADE.md** — turn this into a hosted app for your team (Supabase + Railway) with auth, job history, and a UI.
