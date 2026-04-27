"""Integration tests for the People Intel pipeline."""
import pytest
import inspect

from app.services.linkedin_search import (
    batch_linkedin_search,
    parse_people_input,
    _detect_separator,
)


def test_people_pipeline_has_required_functions():
    """Verify the people pipeline exports expected functions."""
    from app.workers import people_pipeline

    assert hasattr(people_pipeline, "run_people_pipeline")
    assert inspect.iscoroutinefunction(people_pipeline.run_people_pipeline)


def test_linkedin_search_module_exports():
    """Verify the LinkedIn search module exports expected functions."""
    from app.services import linkedin_search

    assert hasattr(linkedin_search, "search_linkedin_profile")
    assert hasattr(linkedin_search, "batch_linkedin_search")
    assert hasattr(linkedin_search, "parse_people_input")
    assert inspect.iscoroutinefunction(linkedin_search.search_linkedin_profile)
    assert inspect.iscoroutinefunction(linkedin_search.batch_linkedin_search)


def test_people_router_exports():
    """Verify the people router exports expected endpoints."""
    from app.routers import people

    assert hasattr(people, "router")
    route_paths = [r.path for r in people.router.routes]
    assert any("/extract" in p for p in route_paths)
    assert any("/download/{job_id}" in p for p in route_paths)


def test_separator_detection():
    """Integration test for separator detection across input styles."""
    assert _detect_separator(["a, b", "c, d", "e, f"]) == ", "
    assert _detect_separator(["a | b", "c | d"]) == " | "
    assert _detect_separator(["a - b", "c - d", "e - f"]) == " - "
    # No separators defaults to comma
    assert _detect_separator(["just names"]) == ", "


def test_parse_people_input_large_batch():
    """Verify parsing handles 100 lines correctly."""
    lines = [f"Person {i}, Company {i}" for i in range(100)]
    items, errors = parse_people_input(lines)
    assert len(items) == 100
    assert errors == 0
    assert items[50]["full_name"] == "Person 50"
    assert items[50]["company_name"] == "Company 50"


def test_parse_people_input_all_bad_lines():
    """Verify all-error input returns zero items."""
    lines = ["no separator here", "also no separator", "nope"]
    items, errors = parse_people_input(lines)
    assert len(items) == 0
    assert errors == 3


def test_parse_people_input_empty():
    """Verify empty input is handled."""
    items, errors = parse_people_input([])
    assert len(items) == 0
    assert errors == 0


@pytest.mark.asyncio
async def test_batch_linkedin_search_empty_input():
    """Verify batch search handles empty input."""
    results = await batch_linkedin_search([], concurrency=5)
    assert results == []


def test_people_router_csv_headers_match_row_length():
    """Verify CSV header count matches row output count."""
    from app.routers.people import _build_people_headers, _extract_people_row

    # People Intel doesn't scrape, so industry/target_market/homepage_raw_text
    # are typically all off — but the CSV must still line up if a legacy job
    # had them on. Cover the all-on case.
    options = {
        "industry_description": True,
        "target_market": True,
        "company_people": True,
        "homepage_raw_text": True,
    }
    headers = _build_people_headers(options)

    class FakeResult:
        input_data = {"full_name": "Test", "company_name": "TestCo"}
        search_results = {"linkedin_url": "https://linkedin.com/in/test", "confidence": 0.9}
        normalized_domain = "test.com"
        raw_domain = "test.com"
        extracted_data = {"industry": "Tech", "niche": "SaaS"}
        contacts = [{"title": "CEO", "first_name": "A", "last_name": "B", "email": "a@b.com", "phone": "", "linkedin_url": ""}]
        status = "extracted"

    row = _extract_people_row(FakeResult(), options)
    assert len(headers) == len(row), f"Headers ({len(headers)}) != Row ({len(row)})"

    # And verify the empty-options case (the new People Intel default).
    bare_headers = _build_people_headers({})
    bare_row = _extract_people_row(FakeResult(), {})
    assert len(bare_headers) == len(bare_row)
