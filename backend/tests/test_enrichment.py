"""Unit tests for enrichment service."""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.enrichment import enrich_company


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
