# QuickEnrich G2 Intel — Standard Operating Procedure

A playbook for running this tool reliably, at scale, without burning through credits or hitting rate limits.

## Daily run — the happy path

```bash
python run.py --categories product-analytics,crm --max 25 --contacts 1 --output $(date +%Y-%m-%d)-leads.csv
```

That's 50 companies enriched with contacts, saved with today's date. Takes ~15–20 min.

## Picking categories

Browse `intel/categories.py` — there are ~175 G2 categories. Best yields for B2B outreach:

| Category group | Good for | Example slugs |
|---|---|---|
| Sales tools | Selling into sales teams | `sales-intelligence`, `sales-engagement`, `conversation-intelligence` |
| Marketing | Marketing ops targets | `marketing-automation`, `email-marketing`, `seo-tools` |
| Analytics | Technical buyers | `product-analytics`, `business-intelligence-bi`, `customer-data-platform-cdp` |
| HR | People ops | `applicant-tracking-systems-ats`, `recruiting`, `onboarding` |
| Finance | Finance ops | `accounts-payable`, `expense-management`, `accounting` |

**Rule of thumb:** narrower categories = better targeting. "CRM" has 300+ products but most won't be your ICP. "Sales Coaching" has 70 products, much tighter fit.

## Cost math (estimates, actual varies)

Per company enriched:
- **Scrape.do:** 1 homepage + 3 internal pages. With super_proxy+render (needed for the G2 discovery page): ~25 credits for the discovery, then ~5–10 credits per company = ~$0.02–0.04 per company
- **Serper:** 1 search per company = ~$0.001
- **Gemini:** ~4k tokens per extraction = fraction of a cent on free tier
- **QuickEnrich:** depends on your plan

**Rough total: $0.04–0.06 per enriched company.** A 100-company daily run ≈ $4–6.

## Scaling to hundreds

- Run overnight: `python run.py ... &` and let it finish
- Raise `--concurrency` to 8 if you have no scrape.do rate-limit errors. 16 if you're on their higher tiers.
- For >500 companies per run, batch into multiple invocations by category — easier to resume if the script crashes.

## Handling failures

The script is idempotent — if you re-run it, nothing is cached locally, so you'll re-burn credits. To avoid this:

1. Run once, save CSV as `run-1.csv`
2. Filter rows with `domain == ""` (failures) into a smaller CSV
3. Hand-inspect to see why — DataDome block? bad Serper match? LLM timeout?
4. Re-run only the failed slice

For production use, consider the upgrade path (UPGRADE.md) which adds Redis caching.

## Good defaults per use case

**Researching a list for cold email:** `--max 25 --contacts 1 --titles "VP Sales,Head of Sales,CMO"` — gets the decision-maker per company.

**Market mapping:** `--max 100 --contacts 0` — skip contact enrichment, just want the landscape.

**Deep dive on a category:** `--max 200 --contacts 2 --concurrency 6` — full listing, two contacts per company.

## What can go wrong

**DataDome-style blocks on G2 category page** — Without `SCRAPE_DO_API_KEY`, the script will fall back to Serper search which returns ~10 products per category. The CSV will say you "found 10" when the real category has 80. Always set the scrape.do key if you can.

**Serper picks wrong domain** — Some product names are generic ("Pipeline", "Flow", "Launch") and Serper's top result may be a marketing blog instead of the product. The `domain` column will show this; filter them in post.

**LLM returns empty intel** — Usually means the scraped site had <200 chars of useful text (splash page, heavy-JS app, or 403). The scraper tries 3 passes before giving up.

**Script hangs** — `httpx` default timeout is 60s per request. If a site is very slow, tune `SCRAPE_TIMEOUT` in `.env`.

## Sharing results

The CSV is safe to email or upload to Google Sheets. Don't include the `.env` file when sharing — it has your API keys.
