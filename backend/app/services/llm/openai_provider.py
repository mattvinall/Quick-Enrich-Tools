import json
import openai as openai_module
from openai import AsyncOpenAI

from app.config import settings
from app.services.llm.base import BaseLLMProvider, VerificationResult
from app.services.retry import retry_async

_PROMPT_TEMPLATE = """\
You are a domain verification assistant. For each company below, determine whether the candidate domain is the official website of that company.

You are given ALL search results (up to 3) so you can compare alternatives. The candidate_domain is from the top result, but it may not be correct — always check the other results too.

Rules:
- A domain MATCHES if it is the primary official website for the company.
- A domain does NOT match if it belongs to a social network (linkedin.com, facebook.com, twitter.com, instagram.com, youtube.com, etc.) or a business directory (yelp.com, yellowpages.com, crunchbase.com, glassdoor.com, bbb.org, etc.).
- Compare the candidate domain against ALL search results. If a different result has a domain that better matches the company name and location, set match=false and suggest that better domain instead.
- Be wary of similar-but-different domains (e.g. "acme.com" vs "acmeinc.com") — verify the snippet/title actually refers to the right organization.
- Use the location to disambiguate companies with similar names. If the snippet references a different city/state than the provided location, lower your confidence.
- confidence is a float between 0.0 and 1.0 representing how certain you are.

Respond with a JSON object containing a single key "results" whose value is an array. Each element must have exactly these keys:
  row_index (integer), match (boolean), confidence (float), reason (string), suggested_domain (string or null)

Companies to verify:
{items}
"""


def _build_items_block(batch: list[dict]) -> str:
    lines: list[str] = []
    for item in batch:
        header = (
            f"- row_index={item['row_index']} | company=\"{item['company_name']}\" | "
            f"location=\"{item.get('location', '')}\" | candidate_domain=\"{item['candidate_domain']}\""
        )
        lines.append(header)
        search_results = item.get("search_results", [])
        if isinstance(search_results, list):
            for i, sr in enumerate(search_results[:3]):
                domain = sr.get("domain", "")
                title = sr.get("title", "")
                snippet = sr.get("snippet", "")
                lines.append(f"    result_{i+1}: domain=\"{domain}\" | title=\"{title}\" | snippet=\"{snippet}\"")
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


class OpenAIProvider(BaseLLMProvider):
    def __init__(self) -> None:
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)

    @property
    def max_batch_size(self) -> int:
        return 20

    async def verify_domains(self, batch: list[dict]) -> list[VerificationResult]:
        prompt = _PROMPT_TEMPLATE.format(items=_build_items_block(batch))

        try:
            response = await retry_async(
                lambda: self._client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    temperature=0.1,
                ),
                max_retries=3,
                base_delay=1.0,
                retryable_exceptions=(
                    openai_module.RateLimitError,
                    openai_module.APIConnectionError,
                    openai_module.InternalServerError,
                ),
            )
        except Exception:
            return _fallback(batch)

        raw = (response.choices[0].message.content or "").strip()

        try:
            parsed_obj: dict = json.loads(raw)
            parsed: list[dict] = parsed_obj["results"]
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
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
