"""Tests for the intel_extracted CSV flag added to all download routers.

The flag tells the user which rows have full company intel (industry,
description, etc.) vs contacts-only — needed because a row with
status='enriched' only guarantees QuickEnrich contacts were found, not
that the homepage scrape + LLM extraction succeeded.
"""
from types import SimpleNamespace

import pytest


# ── Helper-level coverage ─────────────────────────────────────────────


@pytest.mark.parametrize("module_name", [
    "app.routers.funding",
    "app.routers.maps",
    "app.routers.g2",
    "app.routers.intel",
    "app.routers.people",
])
def test_intel_extracted_flag_empty(module_name):
    """No extracted_data → 'false' on every router."""
    import importlib
    mod = importlib.import_module(module_name)
    assert mod._intel_extracted_flag({}) == "false"
    assert mod._intel_extracted_flag(None) == "false"  # type: ignore[arg-type]


@pytest.mark.parametrize("module_name", [
    "app.routers.funding",
    "app.routers.maps",
    "app.routers.g2",
    "app.routers.intel",
    "app.routers.people",
])
@pytest.mark.parametrize("intel_field", [
    "industry", "niche", "description",
    "target_market", "case_studies", "homepage_raw_text",
])
def test_intel_extracted_flag_true_when_any_field(module_name, intel_field):
    """Any single intel field present → 'true'."""
    import importlib
    mod = importlib.import_module(module_name)
    assert mod._intel_extracted_flag({intel_field: "x"}) == "true"


@pytest.mark.parametrize("module_name", [
    "app.routers.funding",
    "app.routers.maps",
    "app.routers.g2",
    "app.routers.intel",
    "app.routers.people",
])
def test_intel_extracted_flag_false_when_only_unrelated_keys(module_name):
    """Fields that aren't intel (general_emails, address) don't count."""
    import importlib
    mod = importlib.import_module(module_name)
    assert mod._intel_extracted_flag({"general_emails": ["a@b.com"]}) == "false"
    assert mod._intel_extracted_flag({"address": "123 Main"}) == "false"


# ── Row-level coverage: column appears in the right position ──────────


def _funding_result(extracted_data, contacts=None):
    return SimpleNamespace(
        input_data={
            "company_name": "Acme",
            "funding_amount": "$5M",
            "funding_round": "Seed",
            "lead_investor": "VC One",
            "funding_description": "Money raised.",
            "source_url": "https://news.example/1",
            "source_name": "Example",
        },
        extracted_data=extracted_data,
        normalized_domain="acme.com",
        raw_domain="acme.com",
        status="enriched",
        contacts=contacts or [],
    )


def test_funding_row_includes_intel_extracted_true():
    from app.routers.funding import _extract_funding_rows, _build_funding_headers
    options = {"industry_description": True, "company_people": True}
    headers = _build_funding_headers(options)
    rows = _extract_funding_rows(
        _funding_result({"industry": "SaaS", "description": "..."}),
        options,
    )
    idx = headers.index("intel_extracted")
    assert rows[0][idx] == "true"


def test_funding_row_includes_intel_extracted_false():
    """Status='enriched' but no intel keys → flag must say false."""
    from app.routers.funding import _extract_funding_rows, _build_funding_headers
    options = {"industry_description": True, "company_people": True}
    headers = _build_funding_headers(options)
    rows = _extract_funding_rows(_funding_result({}), options)
    idx = headers.index("intel_extracted")
    assert rows[0][idx] == "false"


def test_funding_intel_extracted_propagates_across_contact_rows():
    """When a company has multiple contacts, every row carries the same flag."""
    from app.routers.funding import _extract_funding_rows, _build_funding_headers
    options = {"industry_description": True, "company_people": True}
    headers = _build_funding_headers(options)
    contacts = [
        {"title": "CEO", "first_name": "A", "last_name": "B", "email": "a@b.com",
         "phone": "1", "linkedin_url": "ln1"},
        {"title": "CTO", "first_name": "C", "last_name": "D", "email": "c@d.com",
         "phone": "2", "linkedin_url": "ln2"},
    ]
    rows = _extract_funding_rows(
        _funding_result({"industry": "SaaS"}, contacts=contacts),
        options,
    )
    idx = headers.index("intel_extracted")
    assert len(rows) == 2
    assert all(r[idx] == "true" for r in rows)


def test_intel_router_row_includes_flag():
    from app.routers.intel import _extract_intel_rows, _build_intel_headers
    options = {"industry_description": True, "company_people": True}
    headers = _build_intel_headers(options)
    result = SimpleNamespace(
        input_data={"input": "acme.com"},
        extracted_data={"industry": "SaaS"},
        normalized_domain="acme.com",
        raw_domain="acme.com",
        status="enriched",
        contacts=[],
    )
    rows = _extract_intel_rows(result, options)
    idx = headers.index("intel_extracted")
    assert rows[0][idx] == "true"


def test_g2_router_row_includes_flag():
    from app.routers.g2 import _extract_g2_rows, _build_g2_headers
    options = {"industry_description": True, "company_people": True}
    headers = _build_g2_headers(options)
    result = SimpleNamespace(
        input_data={
            "g2_category": "CRM", "g2_url": "https://g2.com/x", "g2_rating": 4.5,
            "g2_review_count": 100, "input": "Acme",
        },
        extracted_data={},  # no intel
        normalized_domain="acme.com",
        raw_domain="acme.com",
        status="enriched",
        contacts=[],
    )
    rows = _extract_g2_rows(result, options)
    idx = headers.index("intel_extracted")
    assert rows[0][idx] == "false"


def test_maps_router_row_includes_flag():
    from app.routers.maps import _extract_maps_rows, _build_maps_headers
    options = {"industry_description": True, "company_people": True}
    headers = _build_maps_headers(options)
    result = SimpleNamespace(
        input_data={
            "search_term": "plumber", "location": "Miami, FL",
            "business_name": "Acme Plumbing", "category": "Plumber",
        },
        extracted_data={"target_market": "Homeowners"},
        normalized_domain="acme.com",
        raw_domain="acme.com",
        status="enriched",
        contacts=[],
    )
    rows = _extract_maps_rows(result, options)
    idx = headers.index("intel_extracted")
    assert rows[0][idx] == "true"


def test_people_router_row_includes_flag():
    from app.routers.people import _extract_people_row, _build_people_headers
    options = {"industry_description": True, "company_people": True}
    headers = _build_people_headers(options, max_contacts=3)
    result = SimpleNamespace(
        input_data={"full_name": "Alice", "company_name": "Acme"},
        extracted_data={"description": "An SaaS company."},
        normalized_domain="acme.com",
        raw_domain="acme.com",
        status="enriched",
        contacts=[],
    )
    row = _extract_people_row(result, options, max_contacts=3)
    idx = headers.index("intel_extracted")
    assert row[idx] == "true"
