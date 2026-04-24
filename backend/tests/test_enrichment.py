"""Unit tests for enrichment service."""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.enrichment import (
    _contact_passes_title_filter,
    _name_passes_filter,
    _title_matches_strict,
    contact_matches_person_name,
    enrich_company,
)


# ── Title filter — strict CEO/Founder searches ────────────────────────

class TestTitleFilterStrict:
    def test_accepts_plain_ceo(self):
        assert _title_matches_strict("CEO", "ceo") is True
        assert _title_matches_strict("Founder & CEO", "ceo") is True
        assert _title_matches_strict("Chief Executive Officer", "ceo") is False  # full string, "ceo" not a token

    def test_rejects_ea_to_ceo(self):
        assert _title_matches_strict("Executive Assistant to the CEO", "ceo") is False
        assert _title_matches_strict("Senior Executive Assistant, Office of the CEO", "ceo") is False

    def test_rejects_new_office_of_patterns(self):
        # The real regression: "Office of CEO" without "the"
        assert _title_matches_strict("Operations Lead, Office of CEO Shopify Logistics", "ceo") is False
        assert _title_matches_strict("Chief of Staff, Office of CEO", "ceo") is False

    def test_rejects_new_to_ceo_patterns(self):
        # "to CEO" without "the"
        assert _title_matches_strict("Lead Executive Business Partner to CEO", "ceo") is False
        assert _title_matches_strict("Strategic Business Partner to Founder", "founder") is False

    def test_rejects_compound_pipe_title_when_primary_doesnt_match(self):
        # "Senior Partner Development Manager at HubSpot | Founder & CEO"
        # Primary doesn't contain CEO → reject.
        assert _title_matches_strict(
            "Senior Partner Development Manager at HubSpot | Founder & CEO", "ceo"
        ) is False
        assert _title_matches_strict(
            "Business Value Consulting | Stripe Brazil CEO", "ceo"
        ) is False

    def test_accepts_compound_pipe_title_when_primary_matches(self):
        # "Co-Founder & CEO | Board Member" — primary is CEO, secondary is Board Member
        assert _title_matches_strict("Co-Founder & CEO | Board Member", "ceo") is True

    def test_accepts_legitimate_compound_ceo(self):
        # Do NOT reject legit compound C-level roles. The old over-aggressive
        # "manager" / "business partner" entries would have killed these.
        assert _title_matches_strict("CEO & Managing Partner", "ceo") is True
        assert _title_matches_strict("CEO / Asia Regional Manager", "ceo") is True
        assert _title_matches_strict("CEO and Head of Business Development", "ceo") is True

    def test_rejects_assistants(self):
        assert _title_matches_strict("Executive Assistant", "ceo") is False
        assert _title_matches_strict("Senior Analyst, CEO Office Sales Strategy", "ceo") is False


# ── Title filter — non-strict (legit title the user typed) ────────────

class TestTitleFilterPermissive:
    def test_user_searching_for_manager_not_blocked(self):
        # If someone searches for "Manager" directly, disqualifying list
        # must not apply — that's the whole request.
        assert _contact_passes_title_filter("Senior Marketing Manager", ["Manager"]) is True
        assert _contact_passes_title_filter("Office of the CEO Manager", ["Manager"]) is True

    def test_user_searching_for_business_partner_not_blocked(self):
        assert _contact_passes_title_filter("Business Partner to CEO", ["Business Partner"]) is True

    def test_user_searching_for_vp_sales(self):
        assert _contact_passes_title_filter("VP of Sales", ["VP of Sales"]) is True
        assert _contact_passes_title_filter("Director of Sales", ["VP of Sales"]) is False


# ── Name placeholder filter ───────────────────────────────────────────

class TestNameFilter:
    def test_rejects_sample_contact(self):
        assert _name_passes_filter("Brian", "Halligan (Sample Contact)") is False
        assert _name_passes_filter("Brian Halligan", "(Sample Contact)") is False

    def test_rejects_test_contact(self):
        assert _name_passes_filter("Test", "Contact") is False

    def test_accepts_real_names(self):
        assert _name_passes_filter("Brian", "Halligan") is True
        assert _name_passes_filter("Tobias", "Lütke") is True


# ── Person name matching (People Intel 1:1) ───────────────────────────

class TestPersonNameMatching:
    def test_exact_match(self):
        assert contact_matches_person_name("Aaron", "Levie", "Aaron Levie") is True

    def test_diacritic_stripping(self):
        # Shopify's CEO — input without umlaut, QE returns with.
        assert contact_matches_person_name("Tobias", "Lütke", "Tobi Lutke") is True

    def test_first_name_prefix_variant(self):
        # Pat/Patrick — shares 'pa' prefix.
        assert contact_matches_person_name("Pat", "Collison", "Patrick Collison") is True
        assert contact_matches_person_name("Patrick", "Collison", "Pat Collison") is True

    def test_last_name_mismatch_rejects(self):
        # Different last names → reject.
        assert contact_matches_person_name("Carlos", "Minetti", "Patrick Collison") is False
        assert contact_matches_person_name("Arash", "Ferdowsi", "Drew Houston") is False

    def test_different_first_name_same_last_rejects(self):
        # Same last name but first names don't share a 2-char prefix.
        assert contact_matches_person_name("Jane", "Halligan", "Brian Halligan") is False

    def test_single_name_is_permissive(self):
        # When we can't split the input into first/last, don't reject anything
        # (better to pass through than silently drop everything).
        assert contact_matches_person_name("Random", "Person", "Madonna") is True

    def test_empty_contact_first_name(self):
        # Some QE rows have only last_name — accept if last name matches.
        assert contact_matches_person_name("", "Halligan", "Brian Halligan") is True

    def test_handles_placeholder_in_last_name(self):
        # QE's "(Sample Contact)" in the last_name — normalization strips
        # parens and symbols, leaving "halligan sample contact", which
        # tokenizes to a different set than "halligan" alone.
        assert contact_matches_person_name(
            "Brian", "Halligan (Sample Contact)", "Brian Halligan"
        ) is False





@pytest.mark.asyncio
async def test_enrich_company_extracts_mobile_field():
    """QuickEnrich returns employee_mobile; it should surface in contacts[0]['mobile']."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = [
        {
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@acme.com",
            "title": "CEO",
            "employee_phone": "+1-555-0100",
            "employee_mobile": "+1-555-0199",
            "employee_linkedin": "https://linkedin.com/in/ada",
        }
    ]

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_response

    with patch("app.services.enrichment.cache_get", return_value=None), \
         patch("app.services.enrichment.cache_set", return_value=None):
        contacts = await enrich_company(
            mock_client, "acme.com", ["CEO"], max_contacts=1, api_key="test-key"
        )

    assert len(contacts) == 1
    assert contacts[0]["phone"] == "+1-555-0100"
    assert contacts[0]["mobile"] == "+1-555-0199"


@pytest.mark.asyncio
async def test_batch_enrich_reports_per_domain_errors(monkeypatch):
    """When a domain's enrichment throws, batch_enrich returns an error marker, not []."""
    from app.services.enrichment import batch_enrich, EnrichmentOutcome

    async def ok_domain(client, domain, job_titles, max_contacts, api_key=None):
        return [{"title": "CEO", "first_name": "A", "last_name": "B", "email": "", "phone": "", "mobile": "", "linkedin_url": ""}]

    async def broken_domain(client, domain, job_titles, max_contacts, api_key=None):
        raise httpx.HTTPStatusError("429 Too Many Requests", request=None, response=MagicMock(status_code=429))

    async def route(client, domain, job_titles, max_contacts, api_key=None):
        if domain == "ok.com":
            return await ok_domain(client, domain, job_titles, max_contacts, api_key=api_key)
        return await broken_domain(client, domain, job_titles, max_contacts, api_key=api_key)

    monkeypatch.setattr("app.services.enrichment.enrich_company", route)

    outcomes = await batch_enrich(
        {"ok.com": [0], "broken.com": [1]},
        job_titles=["CEO"],
        max_contacts=1,
    )

    assert isinstance(outcomes["ok.com"], EnrichmentOutcome)
    assert outcomes["ok.com"].error is None
    assert len(outcomes["ok.com"].contacts) == 1

    assert isinstance(outcomes["broken.com"], EnrichmentOutcome)
    assert outcomes["broken.com"].error is not None
    assert outcomes["broken.com"].contacts == []
