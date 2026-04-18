"""LLM verifiers must mark parse/transport failures separately from a real no-match."""
from unittest.mock import MagicMock, patch

import pytest

from app.services.llm.base import VerificationResult
from app.services.llm.gemini import GeminiProvider


@pytest.mark.asyncio
async def test_gemini_fallback_marks_errored_true():
    provider = GeminiProvider()
    batch = [{
        "row_index": 7, "company_name": "Acme", "location": "",
        "candidate_domain": "acme.com", "search_results": [],
    }]

    # Force parse failure: return non-JSON
    fake_response = MagicMock(); fake_response.text = "not json"
    with patch.object(provider, "_model") as mock_model:
        mock_model.generate_content_async.return_value = fake_response
        results = await provider.verify_domains(batch)

    assert len(results) == 1
    assert results[0].row_index == 7
    assert results[0].match is False
    assert results[0].errored is True, "parse failures must set errored=True"


def test_verification_result_legit_no_match_is_not_errored():
    """A real LLM response saying 'no match' should have errored=False."""
    vr = VerificationResult(
        row_index=1, match=False, confidence=0.9,
        reason="LinkedIn profile, not official site",
        suggested_domain=None,
    )
    assert vr.errored is False
