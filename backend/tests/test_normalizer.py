"""Tests for app.services.normalizer."""

import pytest

from app.services.normalizer import (
    clean_url,
    is_blocked_domain,
    normalize_domain,
)


# ---------------------------------------------------------------------------
# clean_url
# ---------------------------------------------------------------------------


def test_clean_url_strips_protocol_http() -> None:
    assert clean_url("http://example.com") == "example.com"


def test_clean_url_strips_protocol_https() -> None:
    assert clean_url("https://example.com") == "example.com"


def test_clean_url_strips_www() -> None:
    assert clean_url("https://www.example.com") == "example.com"


def test_clean_url_strips_path() -> None:
    assert clean_url("https://example.com/about/us?ref=nav#top") == "example.com"


def test_clean_url_strips_query_only() -> None:
    assert clean_url("https://example.com?foo=bar") == "example.com"


def test_clean_url_strips_fragment_only() -> None:
    assert clean_url("https://example.com#section") == "example.com"


def test_clean_url_handles_subdomain() -> None:
    """Subdomains are collapsed to the root domain."""
    assert clean_url("https://blog.example.com/post/1") == "example.com"


def test_clean_url_preserves_co_uk() -> None:
    """Multi-part TLDs such as co.uk must be preserved in full."""
    assert clean_url("https://www.bbc.co.uk/news") == "bbc.co.uk"


def test_clean_url_no_protocol_no_www() -> None:
    assert clean_url("example.com") == "example.com"


def test_clean_url_invalid_returns_none() -> None:
    assert clean_url("not-a-domain") is None


def test_clean_url_empty_returns_none() -> None:
    assert clean_url("") is None


# ---------------------------------------------------------------------------
# is_blocked_domain
# ---------------------------------------------------------------------------


def test_is_blocked_domain_facebook() -> None:
    assert is_blocked_domain("facebook.com") is True


def test_is_blocked_domain_linkedin() -> None:
    assert is_blocked_domain("linkedin.com") is True


def test_is_blocked_domain_acme() -> None:
    assert is_blocked_domain("acme.com") is False


def test_is_blocked_domain_unknown() -> None:
    assert is_blocked_domain("somecompany.io") is False


# ---------------------------------------------------------------------------
# normalize_domain
# ---------------------------------------------------------------------------


def test_normalize_domain_basic() -> None:
    result = normalize_domain("https://www.acme.com/products")
    assert result["domain"] == "acme.com"
    assert result["blocked"] is False
    assert result["error"] is None


def test_normalize_domain_blocked() -> None:
    result = normalize_domain("https://www.linkedin.com/company/acme")
    assert result["domain"] is None
    assert result["blocked"] is True
    assert result["error"] == "blocked domain: linkedin.com"


def test_normalize_domain_empty_string() -> None:
    result = normalize_domain("")
    assert result["domain"] is None
    assert result["blocked"] is False
    assert result["error"] == "empty input"


def test_normalize_domain_whitespace_only() -> None:
    result = normalize_domain("   ")
    assert result["domain"] is None
    assert result["blocked"] is False
    assert result["error"] == "empty input"


def test_normalize_domain_invalid_tld() -> None:
    result = normalize_domain("not-a-domain")
    assert result["domain"] is None
    assert result["blocked"] is False
    assert result["error"] == "invalid URL"


def test_normalize_domain_co_uk() -> None:
    result = normalize_domain("https://www.bbc.co.uk/news")
    assert result["domain"] == "bbc.co.uk"
    assert result["blocked"] is False
    assert result["error"] is None
