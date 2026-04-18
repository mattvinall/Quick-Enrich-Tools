"""Unit tests for the intel extractor prompt-length cap."""
from unittest.mock import AsyncMock, patch

import pytest

from app.services import intel_extractor
from app.services.intel_extractor import (
    _MAX_PROMPT_CHARS,
    _build_prompt,
    extract_company_intel,
)


_TRUNCATION_MARKER = "\n\n[...truncated]"


def test_build_prompt_truncates_combined_text_when_over_cap():
    """_build_prompt should cap the combined page text before embedding it."""
    scraped_pages = {
        "https://example.com/a": "A" * 20000,
        "https://example.com/b": "B" * 20000,
    }
    prompt = _build_prompt("example.com", scraped_pages, {"industry_description": True})

    # The combined text section lives between the content fences.
    start = prompt.index("--- WEBSITE CONTENT ---") + len("--- WEBSITE CONTENT ---")
    end = prompt.index("--- END CONTENT ---")
    combined = prompt[start:end]

    # Leading/trailing newlines around the section should be small; cap + marker
    # + a couple of newlines is the absolute ceiling.
    assert len(combined) <= _MAX_PROMPT_CHARS + len(_TRUNCATION_MARKER) + 4
    assert "[...truncated]" in combined


def test_build_prompt_leaves_short_text_untouched():
    """Short inputs should not be truncated or get a truncation marker."""
    scraped_pages = {"https://example.com": "hello world"}
    prompt = _build_prompt("example.com", scraped_pages, {"industry_description": True})
    assert "[...truncated]" not in prompt
    assert "hello world" in prompt


@pytest.mark.asyncio
async def test_extract_company_intel_passes_capped_prompt_to_llm():
    """End-to-end: the prompt actually sent to the LLM is capped."""
    scraped_pages = {
        "https://example.com/a": "A" * 20000,
        "https://example.com/b": "B" * 20000,
    }

    captured = {}

    async def fake_gemini(prompt: str) -> dict:
        captured["prompt"] = prompt
        return {"industry": "test"}

    with patch("app.services.intel_extractor.cache_get", new=AsyncMock(return_value=None)), \
         patch("app.services.intel_extractor.cache_set", new=AsyncMock(return_value=None)), \
         patch.object(intel_extractor.settings, "llm_provider", "gemini"), \
         patch("app.services.intel_extractor._call_gemini", side_effect=fake_gemini):
        await extract_company_intel(
            "example.com", scraped_pages, {"industry_description": True}
        )

    prompt = captured["prompt"]
    # The raw combined input was 40k+ chars; the prompt must be meaningfully
    # smaller than that because the page text section is capped.
    start = prompt.index("--- WEBSITE CONTENT ---") + len("--- WEBSITE CONTENT ---")
    end = prompt.index("--- END CONTENT ---")
    combined = prompt[start:end]
    assert len(combined) <= _MAX_PROMPT_CHARS + len(_TRUNCATION_MARKER) + 4
    assert "[...truncated]" in combined
