"""Tests for funding discovery coverage and partial-failure resilience."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import funding_discovery as fd


def test_funding_queries_cover_later_stages():
    """Query list must reach beyond Series A-C to catch growth/venture-debt rounds."""
    joined = " ".join(fd._FUNDING_QUERIES).lower()
    # Must mention late-stage + alternative funding types
    assert "series d" in joined
    assert "growth" in joined
    assert "venture debt" in joined or "debt" in joined
    # Should include variant verbs
    assert "closes" in joined or "closed" in joined
    assert "raised from" in joined or '"raises"' in joined


def test_deduplicate_keeps_distinct_funding_rounds_for_same_company():
    """Same company name with different funding rounds must survive as separate rows."""
    entries = [
        {
            "company_name": "Acme",
            "funding_round": "Series A",
            "source_url": "https://example.com/a",
            "funding_amount": "$10M",
        },
        {
            "company_name": "Acme",
            "funding_round": "Series B",
            "source_url": "https://example.com/b",
            "funding_amount": "$50M",
        },
    ]
    result = fd._deduplicate_companies(entries)
    rounds = sorted(e["funding_round"] for e in result)
    assert rounds == ["Series A", "Series B"], (
        f"expected both rounds kept, got {rounds}"
    )


def test_deduplicate_merges_exact_duplicates():
    """Same company + same round + same url should collapse to one row."""
    entries = [
        {"company_name": "Acme", "funding_round": "Seed", "source_url": "u"},
        {"company_name": "Acme", "funding_round": "Seed", "source_url": "u"},
    ]
    result = fd._deduplicate_companies(entries)
    assert len(result) == 1


@pytest.mark.asyncio
async def test_extract_funding_data_retries_failed_batch_once():
    """A batch that throws once must be retried before being dropped."""
    call_count = {"n": 0}

    class FakeResponse:
        text = '[{"item_index":0,"is_funding_round":true,"company_name":"Acme","funding_amount":"$1M","funding_round":"Seed","lead_investor":null,"description_snippet":null}]'

    def flaky(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("first try fails")
        return FakeResponse()

    with patch("app.services.funding_discovery.genai") as mock_genai:
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = flaky
        mock_genai.GenerativeModel.return_value = mock_model
        mock_genai.GenerationConfig = MagicMock()

        articles = [{"title": "Acme raises $1M", "snippet": "...", "link": "u"}]
        result = await fd._extract_funding_data(articles)

    assert len(result) == 1, f"expected retry to succeed, got {result}"
    assert call_count["n"] == 2
