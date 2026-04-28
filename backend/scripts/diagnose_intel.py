"""Probe why LLM intel extraction is returning empty for so many domains.

Runs the same scrape -> intel_extractor pipeline as the worker but prints
what's happening at each step: scrape success, page count, char counts,
LLM request, LLM response shape, finish reasons. Use to triage a batch of
"extract_failed" domains without having to read Railway logs.

Usage (from backend/):
    python scripts/diagnose_intel.py sereact.ai snabbit.com prometheus.io
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Load backend/.env (same minimal loader as rerun_funding_enrichment.py).
def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app.services.scraper import crawl_site  # noqa: E402


OPTIONS = {
    "industry_description": True,
    "target_market": True,
    "company_people": False,
    "homepage_raw_text": False,
}


async def probe(domain: str) -> None:
    print(f"\n{'='*70}\n{domain}\n{'='*70}")

    scrape_key = os.environ.get("SCRAPE_DO_API_KEY", "")

    async with httpx.AsyncClient() as client:
        try:
            pages = await crawl_site(client, domain, OPTIONS, api_key=scrape_key)
        except Exception as exc:
            print(f"  CRAWL CRASH: {type(exc).__name__}: {exc}")
            return

    if not pages:
        print(f"  CRAWL: no pages returned")
        return

    total_chars = sum(len(t) for t in pages.values())
    print(f"  CRAWL: {len(pages)} pages, {total_chars} total chars")
    for url, text in pages.items():
        print(f"    {url} -> {len(text)} chars")

    # Now run the LLM. Import here so the .env is loaded first.
    import google.generativeai as genai

    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    if not gemini_key:
        print(f"  LLM SKIP: GEMINI_API_KEY missing")
        return

    genai.configure(api_key=gemini_key)
    model = genai.GenerativeModel("gemini-2.5-flash")

    combined = "\n\n---\n\n".join(f"[Page: {u}]\n{t}" for u, t in pages.items())
    if len(combined) > 16000:
        combined = combined[:16000] + "\n\n[...truncated]"

    prompt = f"""You are a business intelligence analyst. Extract structured data from this company's website content.

Company website: {domain}

--- WEBSITE CONTENT ---
{combined}
--- END CONTENT ---

Extract: industry, niche, description, target_market, case_studies.
Return ONLY valid JSON. If a field is not found, set it to null."""

    try:
        response = await asyncio.to_thread(
            model.generate_content,
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )
    except Exception as exc:
        print(f"  LLM CRASH: {type(exc).__name__}: {exc}")
        return

    finish_reason = None
    block_reason = None
    try:
        if response.candidates:
            finish_reason = getattr(response.candidates[0], "finish_reason", None)
        if hasattr(response, "prompt_feedback"):
            block_reason = getattr(response.prompt_feedback, "block_reason", None)
    except Exception:
        pass

    try:
        text = response.text
    except (ValueError, AttributeError):
        text = None

    print(f"  LLM: finish_reason={finish_reason} block_reason={block_reason}")
    if text is None:
        print(f"  LLM RESPONSE: <empty / safety-filtered>")
        return
    print(f"  LLM RESPONSE ({len(text)} chars): {text[:400]}")

    try:
        parsed = json.loads(text)
        populated = {k: v for k, v in parsed.items() if v}
        print(f"  PARSED: {len(populated)}/{len(parsed)} fields populated -> {list(populated.keys())}")
    except json.JSONDecodeError as exc:
        print(f"  PARSE FAIL: {exc}")


async def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    for domain in sys.argv[1:]:
        await probe(domain)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
