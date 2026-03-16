import json
import google.generativeai as genai

from app.config import settings
from app.services.llm.base import BaseLLMProvider, VerificationResult

_PROMPT_TEMPLATE = """\
You are a domain verification assistant. For each company below, determine whether the candidate domain is the official website of that company.

Rules:
- A domain MATCHES if it is the primary official website for the company.
- A domain does NOT match if it belongs to a social network (linkedin.com, facebook.com, twitter.com, instagram.com, youtube.com, etc.) or a business directory (yelp.com, yellowpages.com, crunchbase.com, glassdoor.com, bbb.org, etc.).
- Use the search snippet as supporting evidence but do not rely on it exclusively.
- Use the location to disambiguate companies with similar names.
- If the candidate domain does not match, suggest a better domain if you are confident one exists, otherwise leave suggested_domain as null.
- confidence is a float between 0.0 and 1.0 representing how certain you are.

Respond with a JSON array only — no markdown, no extra text. Each element must have exactly these keys:
  row_index (integer), match (boolean), confidence (float), reason (string), suggested_domain (string or null)

Companies to verify:
{items}
"""


def _build_items_block(batch: list[dict]) -> str:
    lines: list[str] = []
    for item in batch:
        lines.append(
            f"- row_index={item['row_index']} | company=\"{item['company_name']}\" | "
            f"location=\"{item.get('location', '')}\" | candidate_domain=\"{item['candidate_domain']}\" | "
            f"snippet=\"{item.get('search_snippet', '')}\""
        )
    return "\n".join(lines)


def _fallback(batch: list[dict]) -> list[VerificationResult]:
    return [
        VerificationResult(
            row_index=item["row_index"],
            match=False,
            confidence=0.0,
            reason="LLM response could not be parsed.",
            suggested_domain=None,
        )
        for item in batch
    ]


class GeminiProvider(BaseLLMProvider):
    def __init__(self) -> None:
        genai.configure(api_key=settings.gemini_api_key)
        self._model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )

    @property
    def max_batch_size(self) -> int:
        return 20

    async def verify_domains(self, batch: list[dict]) -> list[VerificationResult]:
        prompt = _PROMPT_TEMPLATE.format(items=_build_items_block(batch))

        response = await self._model.generate_content_async(prompt)
        raw = response.text.strip()

        try:
            parsed: list[dict] = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return _fallback(batch)

        results: list[VerificationResult] = []
        try:
            for entry in parsed:
                results.append(
                    VerificationResult(
                        row_index=int(entry["row_index"]),
                        match=bool(entry["match"]),
                        confidence=float(entry["confidence"]),
                        reason=str(entry["reason"]),
                        suggested_domain=entry.get("suggested_domain") or None,
                    )
                )
        except (KeyError, TypeError, ValueError):
            return _fallback(batch)

        return results
