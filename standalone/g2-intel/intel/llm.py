"""LLM-based extraction of company intel from scraped text."""

import asyncio
import json
import logging
import os

logger = logging.getLogger(__name__)

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()  # "gemini" or "openai"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
MAX_PROMPT_CHARS = 16_000


def _build_prompt(domain: str, pages: dict[str, str]) -> str:
    combined = "\n\n---\n\n".join(f"[{u}]\n{t}" for u, t in pages.items())
    if len(combined) > MAX_PROMPT_CHARS:
        combined = combined[:MAX_PROMPT_CHARS] + "\n[...truncated]"

    return f"""You are a business intelligence analyst. Extract structured data from this company's website content.

Company website: {domain}

--- WEBSITE CONTENT ---
{combined}
--- END CONTENT ---

Extract the following fields into a JSON object:
  - "industry": string — the company's primary industry (e.g., "SaaS", "Healthcare")
  - "niche": string — the company's specific niche within that industry
  - "description": string — a ~300 word professional description based on the content
  - "target_market": string — description of who the company serves
  - "address": string or null — the company's physical address if found
  - "phone": string or null — the company's main phone number if found
  - "case_studies": list of strings — names of clients/customers mentioned
  - "website_contacts": list of objects — people mentioned, each {{"name": str, "title": str}}

Rules:
- Only include information directly supported by the content.
- Set missing fields to null (or [] for lists).
- Return ONLY valid JSON. No markdown fences, no explanation."""


async def _gemini_call(prompt: str) -> dict:
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)
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
        return json.loads(response.text)
    except (ValueError, AttributeError, json.JSONDecodeError):
        return {}


async def _openai_call(prompt: str) -> dict:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.1,
    )
    try:
        return json.loads(resp.choices[0].message.content or "{}")
    except json.JSONDecodeError:
        return {}


async def extract_intel(domain: str, pages: dict[str, str]) -> dict:
    if not pages:
        return {}
    prompt = _build_prompt(domain, pages)
    try:
        if LLM_PROVIDER == "openai":
            return await _openai_call(prompt)
        return await _gemini_call(prompt)
    except Exception as exc:
        logger.warning("extract_intel fail for %s: %s: %s", domain, type(exc).__name__, exc)
        return {}
