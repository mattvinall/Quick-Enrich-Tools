"""Unit tests for LinkedIn search service."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.linkedin_search import (
    _build_linkedin_query,
    _extract_linkedin_url,
    _score_confidence,
    parse_people_input,
    search_linkedin_profile,
    batch_linkedin_search,
)


# ── Query construction ──────────────────────────────────────────────


class TestBuildLinkedinQuery:
    def test_basic_query(self):
        query = _build_linkedin_query("Fred Smith", "Apple")
        assert query == 'site:linkedin.com/in/ "Fred Smith" "Apple"'

    def test_strips_whitespace(self):
        query = _build_linkedin_query("  Fred Smith  ", "  Apple  ")
        assert query == 'site:linkedin.com/in/ "Fred Smith" "Apple"'

    def test_unicode_names(self):
        query = _build_linkedin_query("José García", "Empresa S.A.")
        assert query == 'site:linkedin.com/in/ "José García" "Empresa S.A."'


# ── URL extraction ──────────────────────────────────────────────────


class TestExtractLinkedinUrl:
    def test_extracts_linkedin_in_url(self):
        results = [
            {"link": "https://www.linkedin.com/in/fredsmith", "title": "Fred Smith", "snippet": "Apple"},
            {"link": "https://example.com/fred", "title": "Fred", "snippet": ""},
        ]
        url = _extract_linkedin_url(results)
        assert url == "https://www.linkedin.com/in/fredsmith"

    def test_strips_query_params(self):
        results = [
            {"link": "https://linkedin.com/in/fredsmith?trk=public_profile", "title": "Fred", "snippet": ""},
        ]
        url = _extract_linkedin_url(results)
        assert url == "https://linkedin.com/in/fredsmith"

    def test_returns_empty_when_no_linkedin(self):
        results = [
            {"link": "https://example.com/fred", "title": "Fred", "snippet": ""},
        ]
        url = _extract_linkedin_url(results)
        assert url == ""

    def test_returns_empty_for_empty_results(self):
        url = _extract_linkedin_url([])
        assert url == ""

    def test_skips_linkedin_company_pages(self):
        results = [
            {"link": "https://linkedin.com/company/apple", "title": "Apple", "snippet": ""},
        ]
        url = _extract_linkedin_url(results)
        assert url == ""


# ── Confidence scoring ──────────────────────────────────────────────


class TestScoreConfidence:
    def test_no_url_returns_zero(self):
        score = _score_confidence("", "Fred Smith", "Apple", [])
        assert score == 0.0

    def test_url_without_name_match(self):
        results = [{"title": "Some Person - Professional", "snippet": "Works at Apple"}]
        score = _score_confidence("https://linkedin.com/in/someperson", "Fred Smith", "Apple", results)
        assert score == 0.5

    def test_url_with_name_match(self):
        results = [{"title": "Fred Smith - CEO at Apple", "snippet": "Works at Apple"}]
        score = _score_confidence("https://linkedin.com/in/fredsmith", "Fred Smith", "Apple", results)
        assert score == 0.9

    def test_url_with_name_no_company(self):
        results = [{"title": "Fred Smith - Professional", "snippet": "Freelancer"}]
        score = _score_confidence("https://linkedin.com/in/fredsmith", "Fred Smith", "Apple", results)
        assert score == 0.8


# ── Input parsing ───────────────────────────────────────────────────


class TestParsePeopleInput:
    def test_comma_separator(self):
        items, errors = parse_people_input(["Fred Smith, Apple", "Jane Doe, Google"])
        assert len(items) == 2
        assert items[0] == {"full_name": "Fred Smith", "company_name": "Apple"}
        assert items[1] == {"full_name": "Jane Doe", "company_name": "Google"}
        assert errors == 0

    def test_pipe_separator(self):
        items, errors = parse_people_input(["Fred Smith | Apple", "Jane Doe | Google"])
        assert len(items) == 2
        assert items[0] == {"full_name": "Fred Smith", "company_name": "Apple"}

    def test_dash_separator(self):
        items, errors = parse_people_input(["Fred Smith - Apple"])
        assert len(items) == 1
        assert items[0] == {"full_name": "Fred Smith", "company_name": "Apple"}

    def test_skips_empty_lines(self):
        items, errors = parse_people_input(["Fred Smith, Apple", "", "  ", "Jane Doe, Google"])
        assert len(items) == 2

    def test_trims_whitespace(self):
        items, errors = parse_people_input(["  Fred Smith  ,  Apple Inc  "])
        assert items[0] == {"full_name": "Fred Smith", "company_name": "Apple Inc"}

    def test_no_separator_counts_as_error(self):
        items, errors = parse_people_input(["Fred Smith", "Jane Doe, Google"])
        assert len(items) == 1
        assert errors == 1

    def test_company_with_comma(self):
        items, errors = parse_people_input(["Fred Smith, Apple, Inc."])
        assert items[0]["full_name"] == "Fred Smith"
        assert items[0]["company_name"] == "Apple, Inc."

    def test_auto_detects_pipe_separator(self):
        items, errors = parse_people_input([
            "Fred Smith | Apple",
            "Jane Doe | Google",
            "Bob Jones | Microsoft",
        ])
        assert len(items) == 3
        assert items[0]["company_name"] == "Apple"

    def test_mixed_separators_picks_most_common(self):
        items, errors = parse_people_input([
            "Fred Smith | Apple",
            "Jane Doe | Google",
            "Bob Jones, Microsoft",
        ])
        # Pipe is more common (2 vs 1), so pipe is chosen
        assert len(items) == 3


# ── Single search ───────────────────────────────────────────────────


class TestSearchLinkedinProfile:
    @pytest.mark.asyncio
    async def test_returns_linkedin_url_on_hit(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "organic": [
                {
                    "title": "Fred Smith - CEO at Apple",
                    "link": "https://www.linkedin.com/in/fredsmith",
                    "snippet": "Fred Smith is the CEO at Apple...",
                },
            ],
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        with patch("app.services.linkedin_search.cache_get", return_value=None), \
             patch("app.services.linkedin_search.cache_set", return_value=None):
            result = await search_linkedin_profile(mock_client, "Fred Smith", "Apple")

        assert result["linkedin_url"] == "https://www.linkedin.com/in/fredsmith"
        assert result["confidence"] == 0.9

    @pytest.mark.asyncio
    async def test_returns_empty_on_no_results(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"organic": []}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        with patch("app.services.linkedin_search.cache_get", return_value=None), \
             patch("app.services.linkedin_search.cache_set", return_value=None):
            result = await search_linkedin_profile(mock_client, "Fred Smith", "Apple")

        assert result["linkedin_url"] == ""
        assert result["confidence"] == 0.0

    @pytest.mark.asyncio
    async def test_uses_cache(self):
        cached = {
            "linkedin_url": "https://linkedin.com/in/cached",
            "confidence": 0.9,
            "query": "cached query",
            "results": [],
        }
        with patch("app.services.linkedin_search.cache_get", return_value=cached):
            mock_client = AsyncMock()
            result = await search_linkedin_profile(mock_client, "Fred Smith", "Apple")

        assert result["linkedin_url"] == "https://linkedin.com/in/cached"
        mock_client.post.assert_not_called()


# ── Batch search ────────────────────────────────────────────────────


class TestBatchLinkedinSearch:
    @pytest.mark.asyncio
    async def test_deduplicates_same_name_company(self):
        call_count = 0

        async def mock_search(client, name, company, api_key=None):
            nonlocal call_count
            call_count += 1
            return {
                "linkedin_url": f"https://linkedin.com/in/{name.lower().replace(' ', '')}",
                "confidence": 0.9,
                "query": f'site:linkedin.com/in/ "{name}" "{company}"',
                "results": [],
            }

        rows = [
            {"full_name": "Fred Smith", "company_name": "Apple"},
            {"full_name": "Fred Smith", "company_name": "Apple"},  # duplicate
            {"full_name": "Jane Doe", "company_name": "Google"},
        ]

        with patch("app.services.linkedin_search.search_linkedin_profile", side_effect=mock_search), \
             patch("app.services.linkedin_search.cache_get", return_value=None):
            results = await batch_linkedin_search(rows, concurrency=5)

        assert len(results) == 3
        # Fred Smith searched only once (dedup)
        assert call_count == 2
