"""LLM-based company intelligence extraction from scraped website content."""

import asyncio
import json
import logging

from app.config import settings
from app.services.cache import cache_get, cache_set, make_cache_key
from app.services.retry import retry_async

logger = logging.getLogger(__name__)

_MAX_PROMPT_CHARS = 16000  # ~4k tokens, safe across all providers


def _build_field_instructions(options: dict) -> str:
    """Build the dynamic field extraction instructions based on user options."""
    fields: list[str] = []

    if options.get("industry_description"):
        fields.extend([
            '"industry": string — the company\'s primary industry (e.g., "Healthcare", "SaaS", "Manufacturing")',
            '"niche": string — the company\'s specific niche within that industry',
            '"description": string — a ~600 word professional description of the company based on the website content',
            '"address": string or null — the company\'s physical address if found',
            '"phone": string or null — the company\'s main phone number if found',
        ])

    if options.get("target_market"):
        fields.extend([
            '"target_market": string — description of who the company serves / their ideal customer',
            '"case_studies": list of strings — company or organization names mentioned as clients, partners, or in case studies',
        ])

    if options.get("company_people"):
        fields.extend([
            '"website_contacts": list of objects — people found on the website, each with "name" and "title" fields',
        ])

    return "\n".join(f"  - {f}" for f in fields)


def _build_rules(options: dict) -> str:
    """Build conditional rule lines based on which fields are requested."""
    rules: list[str] = []

    if options.get("industry_description"):
        rules.append('- For "description": Write a ~600 word professional description of the company based on the content. Focus on what they do, who they serve, and their value proposition.')
        rules.append('- For "address": Extract the full mailing/office address if found.')
        rules.append('- For "phone": Extract the main company phone number if found.')

    if options.get("target_market"):
        rules.append('- For "case_studies": Extract company/organization names mentioned as clients or in case studies/testimonials. Return as a flat list of strings.')

    if options.get("company_people"):
        rules.append('- For "website_contacts": Extract names and titles of people mentioned on the website (team page, about page, etc.). Each entry should have "name" (string) and "title" (string).')

    return "\n".join(rules) + "\n" if rules else ""


def _build_prompt(domain: str, scraped_pages: dict[str, str], options: dict) -> str:
    """Build the full extraction prompt for the LLM."""
    page_urls = list(scraped_pages.keys())
    combined_text = "\n\n---\n\n".join(
        f"[Page: {url}]\n{text}" for url, text in scraped_pages.items()
    )

    if len(combined_text) > _MAX_PROMPT_CHARS:
        combined_text = combined_text[:_MAX_PROMPT_CHARS] + "\n\n[...truncated]"
        logger.info(
            "intel_extractor: truncated combined page text for %s to %d chars",
            domain, _MAX_PROMPT_CHARS,
        )

    field_instructions = _build_field_instructions(options)

    return f"""You are a business intelligence analyst. Extract structured data from this company's website content.

Company website: {domain}
Pages scraped: {', '.join(page_urls)}

--- WEBSITE CONTENT ---
{combined_text}
--- END CONTENT ---

Extract the following fields into a JSON object:
{field_instructions}

Rules:
- Only include information you can directly find or confidently infer from the provided text.
{_build_rules(options)}- If a data point is not found in the content, set it to null (or empty list for list fields).
- Return ONLY valid JSON. No markdown, no explanation, just the JSON object."""


async def _call_gemini(prompt: str) -> dict:
    """Call Gemini API directly for intel extraction."""
    import google.generativeai as genai

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")

    response = await asyncio.to_thread(
        model.generate_content,
        prompt,
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json",
            temperature=0.1,
        ),
    )
    try:
        text = response.text
    except (ValueError, AttributeError):
        # Safety-filtered or empty candidates — nothing usable
        return {}
    return json.loads(text)


async def _call_openai(prompt: str) -> dict:
    """Call OpenAI API directly for intel extraction."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.1,
    )
    content = response.choices[0].message.content or "{}"
    return json.loads(content)


async def extract_company_intel(
    domain: str,
    scraped_pages: dict[str, str],
    options: dict,
) -> dict:
    """Extract structured company intelligence from scraped website text.

    Uses LLM (Gemini or OpenAI) based on settings.llm_provider.
    Checks cache first. Returns extracted data dict.
    """
    # Check cache
    option_str = json.dumps(options, sort_keys=True)
    cache_key = make_cache_key("intel", domain.lower(), option_str)
    cached = await cache_get(cache_key)
    if cached is not None:
        logger.info("INTEL CACHE HIT: %s", domain)
        return cached

    if not scraped_pages:
        return {}

    prompt = _build_prompt(domain, scraped_pages, options)

    try:
        if settings.llm_provider == "openai":
            result = await retry_async(
                lambda: _call_openai(prompt),
                max_retries=3,
                base_delay=1.0,
            )
        else:
            result = await retry_async(
                lambda: _call_gemini(prompt),
                max_retries=3,
                base_delay=1.0,
            )

        await cache_set(cache_key, result, settings.cache_ttl_days)
        return result

    except Exception as exc:
        logger.warning("extract_company_intel failed for %s: %s", domain, exc)
        return {}


async def batch_extract_intel(
    items: list[dict],
    concurrency: int | None = None,
) -> dict[str, dict]:
    """Extract intel for multiple companies concurrently.

    Each item: {"domain": str, "scraped_pages": dict, "options": dict}
    Returns {domain: extracted_data_dict}.
    """
    limit = concurrency if concurrency is not None else settings.intel_extraction_concurrency
    semaphore = asyncio.Semaphore(limit)

    results: dict[str, dict] = {}

    async def _extract_one(item: dict) -> tuple[str, dict]:
        domain = item["domain"]
        async with semaphore:
            data = await extract_company_intel(
                domain, item["scraped_pages"], item["options"]
            )
            return domain, data

    tasks = [_extract_one(item) for item in items]
    outcomes = await asyncio.gather(*tasks, return_exceptions=True)

    for outcome in outcomes:
        if isinstance(outcome, BaseException):
            logger.warning("batch_extract_intel error: %s", outcome)
            continue
        domain, data = outcome
        results[domain] = data

    return results
