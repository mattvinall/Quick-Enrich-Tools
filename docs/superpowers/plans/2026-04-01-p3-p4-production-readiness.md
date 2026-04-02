# P3/P4 Production Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the G2 Intel and Company Intel tools production-ready by fixing 10 gaps identified in the design spec.

**Architecture:** Add scrape.do-based G2 category page scraping with Serper fallback to `g2_scraper.py`. Wire serper_api_key and progress feedback through the G2 pipeline. Fix frontend plumbing (error states, missing props, G2 URL column).

**Tech Stack:** Python/FastAPI (backend), Next.js/React (frontend), scrape.do API, Serper API, BeautifulSoup, Redis caching

**Spec:** `docs/superpowers/specs/2026-04-01-p3-p4-production-readiness-design.md`

---

### Task 1: G2 Category Page Scraping via scrape.do (Gaps 1+2+3)

**Files:**
- Modify: `backend/app/services/g2_scraper.py`
- Reference: `backend/app/services/scraper.py` (reuse `scrape_page`)

- [ ] **Step 1: Add new imports to `g2_scraper.py`**

Add these imports to the **existing** import block (do NOT replace existing imports):

```python
from urllib.parse import parse_qs  # add to existing urllib.parse import line
from bs4 import BeautifulSoup  # new
from app.services.scraper import scrape_page  # new — reuse scrape.do integration
```

- [ ] **Step 2: Write `_parse_g2_category_html` function**

Add after existing imports/functions. This parses G2 category listing HTML to extract product cards:

```python
def _parse_g2_category_html(html: str) -> tuple[list[dict], int]:
    """Parse G2 category page HTML to extract product listings.

    Returns (products, total_pages).
    Each product: {name, website, g2_url, rating, review_count}.
    """
    soup = BeautifulSoup(html, "lxml")
    products: list[dict] = []

    # G2 product cards are in div.product-listing or similar containers
    # Try multiple selectors for resilience
    cards = soup.select('[data-product-id]') or soup.select('.product-listing__card') or soup.select('.paper--product')

    for card in cards:
        try:
            # Product name
            name_el = card.select_one('a.product-listing__product-name') or card.select_one('[itemprop="name"]') or card.select_one('h3 a')
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            if not name or len(name) < 2:
                continue

            # G2 URL
            href = name_el.get("href", "")
            if href and not href.startswith("http"):
                href = f"https://www.g2.com{href}"
            slug = ""
            if "/products/" in href:
                parts = urlparse(href).path.strip("/").split("/")
                if len(parts) >= 2 and parts[0] == "products":
                    slug = parts[1]
            g2_url = f"https://www.g2.com/products/{slug}" if slug else href

            # Rating
            rating = None
            rating_el = card.select_one('[itemprop="ratingValue"]') or card.select_one('.star-wrapper__value')
            if rating_el:
                try:
                    rating = float(rating_el.get("content", "") or rating_el.get_text(strip=True))
                except (ValueError, TypeError):
                    pass

            # Review count
            review_count = None
            review_el = card.select_one('[itemprop="reviewCount"]') or card.select_one('.product-listing__review-count')
            if review_el:
                text = review_el.get("content", "") or review_el.get_text(strip=True)
                nums = re.findall(r"[\d,]+", text)
                if nums:
                    try:
                        review_count = int(nums[0].replace(",", ""))
                    except ValueError:
                        pass

            # Website URL — G2 sometimes shows it, sometimes not
            website = None
            website_el = card.select_one('a[href*="visit_website"]') or card.select_one('.product-listing__website')
            if website_el:
                ws_href = website_el.get("href", "")
                # Extract actual domain from G2 redirect URL
                if "url=" in ws_href:
                    qs = parse_qs(urlparse(ws_href).query)
                    ws_href = qs.get("url", [ws_href])[0]
                if ws_href.startswith("http"):
                    parsed = urlparse(ws_href)
                    website = parsed.netloc.removeprefix("www.")

            products.append({
                "name": name,
                "website": website,
                "g2_url": g2_url,
                "rating": rating,
                "review_count": review_count,
            })
        except Exception as exc:
            logger.debug("Failed to parse G2 product card: %s", exc)
            continue

    # Detect total pages from pagination
    total_pages = 1
    pagination = soup.select('a[aria-label*="Page"]') or soup.select('.pagination a')
    for link in pagination:
        text = link.get_text(strip=True)
        try:
            page_num = int(text)
            total_pages = max(total_pages, page_num)
        except ValueError:
            continue

    return products, total_pages
```

- [ ] **Step 3: Write `discover_g2_category_via_scrape` function**

```python
async def discover_g2_category_via_scrape(
    client: httpx.AsyncClient,
    category_slug: str,
    category_name: str,
    max_products: int = 250,
    semaphore: asyncio.Semaphore | None = None,
) -> list[dict] | None:
    """Discover G2 products by scraping category listing pages via scrape.do.

    Returns list of product dicts, or None if scraping failed (caller should fallback to Serper).
    """
    cache_key = make_cache_key("g2_cat_scrape", category_slug, str(max_products))
    try:
        cached = await cache_get(cache_key)
        if cached is not None and isinstance(cached, dict):
            products = cached.get("products", [])
            logger.info("G2 SCRAPE CACHE HIT: %s (%d products)", category_slug, len(products))
            return products[:max_products]
    except Exception:
        pass

    all_products: list[dict] = []
    seen_slugs: set[str] = set()
    max_pages = min(
        max(1, (max_products + 24) // 25),  # ceil(max_products / 25)
        settings.g2_max_pages_per_category,   # enforce config cap
    )

    for page in range(1, max_pages + 1):
        url = f"https://www.g2.com/categories/{category_slug}"
        if page > 1:
            url += f"?page={page}"

        try:
            if semaphore:
                async with semaphore:
                    html = await scrape_page(client, url, render=True)
            else:
                html = await scrape_page(client, url, render=True)
        except Exception as exc:
            logger.warning("G2 scrape.do failed for %s page %d: %s", category_slug, page, exc)
            if page == 1:
                # Page 1 failed — can't scrape this category at all
                return None
            # Later page failed — keep what we have
            break

        products, total_pages = _parse_g2_category_html(html)

        if not products:
            # Empty page or parsing failed completely
            if page == 1:
                return None
            break

        for p in products:
            slug = _extract_product_slug(p.get("g2_url", ""))
            if slug and slug not in seen_slugs:
                seen_slugs.add(slug)
                all_products.append(p)

        logger.info(
            "G2 SCRAPE: %s page %d → %d products (total: %d)",
            category_slug, page, len(products), len(all_products),
        )

        if len(all_products) >= max_products:
            break
        if len(products) < 25:
            break  # Short page means no more results
        if page >= total_pages:
            break

        # Rate limit: 1-2s delay between pages to avoid DataDome
        await asyncio.sleep(1.5)

    result = all_products[:max_products]

    try:
        await cache_set(cache_key, {"products": result}, settings.g2_cache_ttl_days)
    except Exception:
        pass

    return result if result else None
```

- [ ] **Step 4: Update `batch_scrape_g2_categories` to try scrape.do first with progress callback**

Replace the existing `batch_scrape_g2_categories` function:

```python
async def batch_scrape_g2_categories(
    categories: list[str],
    max_per_category: int = 250,
    on_progress: object = None,
) -> list[dict]:
    """Discover products across multiple G2 categories.

    Tries scrape.do first for each category, falls back to Serper on failure.
    Deduplicates across all categories and sources.
    """
    from app.services.g2_categories import get_category_by_slug

    concurrency = settings.g2_scrape_concurrency
    semaphore = asyncio.Semaphore(concurrency)

    all_products: list[dict] = []
    seen_slugs: set[str] = set()
    failed_categories: list[tuple[str, str]] = []  # (slug, name) pairs for Serper fallback
    done_count = 0

    async with httpx.AsyncClient() as client:
        # Phase A: Try scrape.do for each category
        async def _scrape_one(slug: str, name: str) -> tuple[str, list[dict] | None]:
            result = await discover_g2_category_via_scrape(
                client, slug, name, max_per_category, semaphore
            )
            return slug, result

        tasks = []
        for slug in categories:
            cat = get_category_by_slug(slug)
            name = cat["name"] if cat else slug.replace("-", " ").title()
            tasks.append(_scrape_one(slug, name))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for slug, result in zip(categories, results):
            cat = get_category_by_slug(slug)
            name = cat["name"] if cat else slug.replace("-", " ").title()

            if isinstance(result, BaseException):
                logger.warning("G2 scrape.do exception for %s: %s", slug, result)
                failed_categories.append((slug, name))
            else:
                _, products = result
                if products is None:
                    failed_categories.append((slug, name))
                else:
                    for p in products:
                        product_slug = _extract_product_slug(p.get("g2_url", ""))
                        if product_slug and product_slug not in seen_slugs:
                            seen_slugs.add(product_slug)
                            all_products.append({**p, "g2_category": slug})

            done_count += 1
            if on_progress:
                try:
                    await on_progress(done_count, len(categories))
                except Exception:
                    pass

        # Phase B: Serper fallback for failed categories
        if failed_categories:
            logger.info("G2: %d categories falling back to Serper: %s",
                len(failed_categories), [s for s, _ in failed_categories])

            for slug, name in failed_categories:
                try:
                    serper_products = await discover_g2_category(
                        client, slug, name, max_per_category, semaphore
                    )
                    for p in serper_products:
                        product_slug = _extract_product_slug(p.get("g2_url", ""))
                        if product_slug and product_slug not in seen_slugs:
                            seen_slugs.add(product_slug)
                            all_products.append({**p, "g2_category": slug})
                except Exception as exc:
                    logger.warning("G2 Serper fallback failed for %s: %s", slug, exc)

    logger.info("G2 BATCH: %d unique companies from %d categories", len(all_products), len(categories))
    return all_products
```

- [ ] **Step 5: Run a quick manual test**

Test with a small category to verify scrape.do works against G2:
```bash
cd backend && python -c "
import asyncio, httpx
from app.services.scraper import scrape_page
from app.services.g2_scraper import _parse_g2_category_html

async def test():
    async with httpx.AsyncClient() as c:
        html = await scrape_page(c, 'https://www.g2.com/categories/crm', render=True)
        products, pages = _parse_g2_category_html(html)
        print(f'Found {len(products)} products, {pages} total pages')
        for p in products[:3]:
            print(p)

asyncio.run(test())
"
```

If DataDome blocks (empty products list), the Serper fallback handles it automatically.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/g2_scraper.py
git commit -m "feat(g2): add scrape.do-based category discovery with Serper fallback

Scrape G2 category listing pages to get full product lists with
ratings, review counts, and website URLs. Falls back to Serper
per-category if DataDome blocks scrape.do. Includes progress
callback for Phase 0 updates."
```

---

### Task 2: Update G2 Pipeline for Website URLs and Progress (Gaps 3+5)

**Files:**
- Modify: `backend/app/workers/g2_pipeline.py`

- [ ] **Step 1: Update JobResult creation to handle website URLs**

In `run_g2_pipeline`, update the JobResult creation loop to set `input_type: "url"` when a website is available:

Replace lines 87-101 with:

```python
            job_results = [
                JobResult(
                    job_id=parsed_job_id,
                    row_index=batch_start + i,
                    input_data={
                        "input": p.get("website") or p["name"],
                        "input_type": "url" if p.get("website") else "name",
                        "company_name": p["name"],
                        "g2_url": p.get("g2_url", ""),
                        "g2_category": p.get("g2_category", ""),
                        "g2_rating": p.get("rating"),
                        "g2_review_count": p.get("review_count"),
                    },
                    status="pending",
                )
                for i, p in enumerate(batch)
            ]
```

- [ ] **Step 2: Add progress callback to Phase 0**

Replace the `batch_scrape_g2_categories` call and surrounding progress updates (lines 51-55 and 57-58) with:

```python
    async def _on_g2_progress(done: int, total: int) -> None:
        try:
            async with AsyncSessionLocal() as progress_db:
                await update_job_progress(progress_db, parsed_job_id, "g2_scrape", done, total)
        except Exception:
            pass

    try:
        products = await batch_scrape_g2_categories(
            categories, max_per_category, on_progress=_on_g2_progress
        )
    except Exception as exc:
```

Remove the standalone progress update before the scrape call (lines 51-55) since the callback handles it now.

- [ ] **Step 3: Commit**

```bash
git add backend/app/workers/g2_pipeline.py
git commit -m "feat(g2): wire website URLs and progress callback in pipeline

Set input_type to 'url' when G2 scraping finds a website, skipping
the Serper resolve step. Add per-category progress callback for
real-time Phase 0 updates."
```

---

### Task 3: G2 Serper API Key Pass-through (Gaps 4+7)

**Files:**
- Modify: `backend/app/routers/g2.py`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/app/tools/g2-intel/page.tsx`

- [ ] **Step 1: Add serper_api_key to G2ExtractRequest**

In `backend/app/routers/g2.py`, add to `G2ExtractRequest`:

```python
class G2ExtractRequest(BaseModel):
    categories: list[str]
    max_per_category: int = 250
    options: ExtractionOptions
    quickenrich_api_key: str = ""
    serper_api_key: str = ""
    job_titles: list[str] = []
    max_contacts: int = 3
```

Add to `job_config` dict (after line 118):

```python
    job_config = {
        "categories": valid_slugs,
        "max_per_category": body.max_per_category,
        "options": opts.model_dump(),
        "quickenrich_api_key": body.quickenrich_api_key,
        "serper_api_key": body.serper_api_key,
        "job_titles": body.job_titles,
        "max_contacts": body.max_contacts,
    }
```

- [ ] **Step 2: Add serper_api_key to frontend G2ExtractRequest interface**

In `frontend/src/lib/api.ts`, add to `G2ExtractRequest`:

```typescript
export interface G2ExtractRequest {
  categories: string[];
  max_per_category: number;
  options: ExtractionOptions;
  quickenrich_api_key: string;
  serper_api_key: string;
  job_titles: string[];
  max_contacts: number;
}
```

- [ ] **Step 3: Wire Serper API key in G2 page**

In `frontend/src/app/tools/g2-intel/page.tsx`:

Add state after the QuickEnrich API key state (after line 50):
```typescript
  const [serperApiKey, setSerperApiKey] = useState('');
```

Pass props to ExtractionSettings (after line 251):
```tsx
                    <ExtractionSettings
                      ...existing props...
                      hasCompanyNames={true}
                      serperApiKey={serperApiKey}
                      onSerperApiKeyChange={setSerperApiKey}
                    />
```

Add `serper_api_key` to the submit call body (after `max_contacts` at line 135):
```typescript
          max_contacts: companyPeople ? maxContacts : 1,
          serper_api_key: serperApiKey,
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/g2.py frontend/src/lib/api.ts frontend/src/app/tools/g2-intel/page.tsx
git commit -m "feat(g2): add serper_api_key pass-through for G2 frontend and backend"
```

---

### Task 4: Category Fetch Error Handling (Gap 6)

**Files:**
- Modify: `frontend/src/components/G2CategorySelector.tsx`

- [ ] **Step 1: Add error state and retry logic**

Add `error` state and update the fetch effect. Replace lines 27-46:

```typescript
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const searchRef = useRef<HTMLInputElement>(null);

  async function loadCategories() {
    setLoading(true);
    setError('');
    try {
      const data = await getG2Categories();
      setCategories(data.categories);
      setParents(data.parents);
    } catch {
      setError('Failed to load categories. Please check your connection.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadCategories();
  }, []);
```

- [ ] **Step 2: Add error UI in the category list area**

Replace the loading/empty state block (lines 181-188) with:

```tsx
        {loading ? (
          <div className="flex items-center justify-center h-24 text-sm text-text-secondary">
            Loading categories...
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center h-24 gap-2">
            <p className="text-sm text-red-600">{error}</p>
            <button
              type="button"
              onClick={loadCategories}
              className="text-sm font-medium text-primary hover:underline"
            >
              Retry
            </button>
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex items-center justify-center h-24 text-sm text-text-secondary">
            No categories match your search.
          </div>
        ) : (
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/G2CategorySelector.tsx
git commit -m "fix(g2): show error state with retry when category fetch fails"
```

---

### Task 5: G2 URL in CSV and Results (Gap 10)

**Files:**
- Modify: `backend/app/routers/g2.py`

- [ ] **Step 1: Add g2_url to CSV base columns and row extraction**

In `g2.py`, update `_BASE_COLUMNS` (line 148):

```python
_BASE_COLUMNS = ["g2_category", "g2_url", "g2_rating", "g2_review_count", "input", "website", "status"]
```

In `_extract_g2_row`, add after line 157:

```python
    g2_url = input_data.get("g2_url", "")
```

Update the `base` list to include it:

```python
    base = [g2_category, g2_url, g2_rating, g2_review_count, original_input, website, row_status]
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/routers/g2.py
git commit -m "feat(g2): add g2_url column to CSV download"
```

---

### Task 6: Estimated Products Label (Gap 9)

**Files:**
- Modify: `frontend/src/components/G2CategorySelector.tsx`

- [ ] **Step 1: Append "(est.)" to the count display**

In `G2CategorySelector.tsx`, update line 217:

```tsx
                    <span className="text-xs text-text-secondary tabular-nums shrink-0">
                      ~{cat.estimated_products} (est.)
                    </span>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/G2CategorySelector.tsx
git commit -m "fix(g2): add (est.) label to category product counts"
```

---

### Task 7: Verify Phase Name Mapping (Gap 8)

**Files:**
- Reference: `frontend/src/components/ProgressTracker.tsx:54-56`

- [ ] **Step 1: Verify the mapping is correct**

Confirmed from code review: `ProgressTracker.tsx` line 54-56 has:
```typescript
const PHASE_ALIASES: Record<string, string> = {
  g2_scrape: 'discover',
};
```

And `findPhaseIndex` at line 58-62 normalizes the backend phase name to match the frontend phase list. The G2 page passes `PIPELINE_PHASES = ['Discover', 'Resolve', 'Crawl', 'Extract', 'Enrich', 'Deliver']`.

**This mapping is correct. No code changes needed.** Verify visually during testing that the "Discover" step highlights when `g2_scrape` is the current phase.

---

### Task 8: Final Manual Testing Checklist

- [ ] **P3 (Company Intel by URL):**
  - Paste 3-5 URLs → Run Extraction → Verify results download with industry, description, contacts
  - Paste 2-3 company names → Verify Serper resolves them → Same extraction flow
  - Verify generic emails appear in results (regex extraction)
  - Verify scrape.do is used for crawling (check backend logs for `scrape.do` requests)

- [ ] **P4 (G2 Intel):**
  - Select 1 category → Run → Verify companies discovered with ratings/reviews (if scrape.do works) or names only (if Serper fallback)
  - Verify Phase 0 progress updates in real-time
  - Verify Serper API key field appears in Extraction Settings
  - Verify CSV download includes g2_url column
  - Check that companies with websites from G2 skip the Serper resolve step (check backend logs)
  - Verify error state shows with retry button when backend is stopped
