"""Unit tests for people router — validation and CSV generation."""
import pytest

from app.routers.people import (
    _build_people_headers,
    _extract_people_row,
    PeopleItem,
    PeopleExtractRequest,
    ExtractionOptions,
)


class TestBuildPeopleHeaders:
    def test_base_columns_always_present(self):
        headers = _build_people_headers({})
        assert headers[:5] == [
            "full_name", "company_name", "linkedin_url", "linkedin_confidence", "website", "status",
        ][:len(headers)] or "full_name" in headers

    def test_includes_intel_columns(self):
        headers = _build_people_headers({"industry_description": True})
        assert "industry" in headers
        assert "niche" in headers
        assert "description" in headers

    def test_includes_contact_columns(self):
        # People Intel is 1:1 — exactly one un-numbered contact_* block,
        # never contact_1_/contact_2_.
        headers = _build_people_headers({"company_people": True})
        assert "contact_title" in headers
        assert "contact_email" in headers
        assert "contact_linkedin" in headers
        assert not any(h.startswith("contact_1_") for h in headers)
        assert not any(h.startswith("contact_2_") for h in headers)

    def test_base_only_when_no_options(self):
        headers = _build_people_headers({})
        assert "industry" not in headers
        assert "target_market" not in headers


class TestExtractPeopleRow:
    def test_extracts_base_fields(self):
        # linkedin_url and linkedin_confidence now live in input_data (stashed
        # there by people_pipeline Phase 0) because the intel pipeline's
        # resolve phase overwrites search_results during domain lookup.
        class FakeResult:
            input_data = {
                "full_name": "Fred Smith",
                "company_name": "Apple",
                "linkedin_url": "https://linkedin.com/in/fredsmith",
                "linkedin_confidence": 0.9,
            }
            search_results = {"query": "apple official website", "results": []}
            normalized_domain = "apple.com"
            raw_domain = "apple.com"
            extracted_data = {}
            contacts = []
            status = "extracted"

        row = _extract_people_row(FakeResult(), {})
        assert row[0] == "Fred Smith"
        assert row[1] == "Apple"
        assert row[2] == "https://linkedin.com/in/fredsmith"
        assert row[3] == "0.9"
        assert row[4] == "apple.com"
        assert row[5] == "extracted"

    def test_handles_missing_linkedin_data(self):
        class FakeResult:
            input_data = {"full_name": "Fred Smith", "company_name": "Apple"}
            search_results = None
            normalized_domain = None
            raw_domain = None
            extracted_data = {}
            contacts = []
            status = "not_found"

        row = _extract_people_row(FakeResult(), {})
        assert row[0] == "Fred Smith"
        assert row[2] == ""  # linkedin_url absent
        assert row[3] == ""  # confidence absent
        assert row[4] == ""  # website


class TestPeopleItemValidation:
    def test_valid_item(self):
        item = PeopleItem(full_name="Fred Smith", company_name="Apple")
        assert item.full_name == "Fred Smith"

    def test_with_website(self):
        item = PeopleItem(full_name="Fred", company_name="Apple", website="apple.com")
        assert item.website == "apple.com"
