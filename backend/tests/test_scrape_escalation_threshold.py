"""Regression tests for the SPA-shell escalation threshold.

The scraper has a 3-pass strategy: datacenter → render → super+render.
Pass 2/3 only fire when Pass 1 returns less than _MIN_CONTENT_LENGTH chars.

The bug we're guarding against: SPAs return ~250-500 chars of React shell
HTML on a basic fetch. With the old threshold (200 chars), that text was
"long enough" to skip escalation, so the LLM got nothing real to work
with and silently produced empty intel.

The fix bumps the threshold to 1500 so SPA shells trigger Pass 2/3.
"""
import pytest

from app.services import scraper


def test_threshold_is_at_least_spa_shell_size():
    """Threshold must be high enough to catch typical React/Next.js shells.

    A bare React shell rendered without hydration is typically 200-1000
    chars of nav/footer/script tags. 1500 covers the common case while
    still being small enough that it won't fire on real (just terse)
    homepages.
    """
    assert scraper._MIN_CONTENT_LENGTH >= 1500, (
        "Threshold too low — SPA shells (200-1000 chars) won't escalate to "
        "JS-rendered passes, leading to empty LLM extraction."
    )


@pytest.mark.asyncio
async def test_pass1_thin_content_triggers_pass2(monkeypatch):
    """When Pass 1 returns <1500 chars of text, Pass 2 (render) must fire."""
    calls: list[dict] = []

    async def fake_scrape(client, url, render=False, super_proxy=False,
                          block_resources=True, api_key=None):
        calls.append({
            "url": url, "render": render, "super_proxy": super_proxy,
        })
        # Pass 1 (no render): return a thin React-shell-sized HTML
        if not render and not super_proxy:
            return "<html><body><nav>Home</nav><footer>© 2026</footer></body></html>"
        # Pass 2 (render): return rich content well over the threshold
        if render and not super_proxy:
            return "<html><body>" + ("Real homepage content. " * 200) + "</body></html>"
        return "<html><body></body></html>"

    monkeypatch.setattr(scraper, "scrape_page", fake_scrape)

    import httpx
    async with httpx.AsyncClient() as client:
        result = await scraper.crawl_site(
            client, "spa-shell.example", options={}, api_key="test-key", max_pages=1,
        )

    # Pass 1 + Pass 2 should both fire; Pass 3 should NOT (Pass 2 succeeded)
    pass1_calls = [c for c in calls if not c["render"] and not c["super_proxy"]]
    pass2_calls = [c for c in calls if c["render"] and not c["super_proxy"]]
    pass3_calls = [c for c in calls if c["render"] and c["super_proxy"]]

    assert len(pass1_calls) == 1, "Pass 1 should fire exactly once"
    assert len(pass2_calls) == 1, (
        "Pass 2 (render) MUST fire when Pass 1 content is below threshold "
        "— this is the regression we're guarding against"
    )
    assert len(pass3_calls) == 0, (
        "Pass 3 should not fire once Pass 2 produced enough content"
    )

    # And the final stored content should be the rich Pass 2 output
    homepage_url = "https://spa-shell.example"
    assert len(result[homepage_url]) > 1500


@pytest.mark.asyncio
async def test_pass1_rich_content_skips_escalation(monkeypatch):
    """When Pass 1 already returns rich content, Pass 2/3 must NOT fire.

    Guards against the threshold being set so high that ALL sites
    escalate, burning Scrape.do credits unnecessarily.
    """
    calls: list[dict] = []

    async def fake_scrape(client, url, render=False, super_proxy=False,
                          block_resources=True, api_key=None):
        calls.append({"render": render, "super_proxy": super_proxy})
        # Pass 1 returns plenty of content — way over threshold
        if not render and not super_proxy:
            return "<html><body>" + ("Real homepage content. " * 200) + "</body></html>"
        return ""

    monkeypatch.setattr(scraper, "scrape_page", fake_scrape)

    import httpx
    async with httpx.AsyncClient() as client:
        await scraper.crawl_site(
            client, "rich-site.example", options={}, api_key="test-key", max_pages=1,
        )

    pass2_or_3 = [c for c in calls if c["render"] or c["super_proxy"]]
    assert len(pass2_or_3) == 0, (
        "Rich Pass 1 content should not trigger render escalation — "
        "we'd be burning Scrape.do credits unnecessarily."
    )
