"""6-phase pipeline for company intelligence extraction.

Phases: Resolve → Verify → Crawl → Extract → Enrich → Deliver
Uses bounded asyncio.Queue for backpressure between phases.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

import tldextract
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import EmailCapture, Job, JobResult
from app.services.email_service import send_results_email
from app.services.enrichment import batch_enrich
from app.services.scraper import batch_crawl, extract_generic_emails
from app.services.intel_extractor import batch_extract_intel
from app.services.serper import batch_search

logger = logging.getLogger(__name__)

QueueItem = list[uuid.UUID] | None


def _classify_input(line: str) -> tuple[str, str]:
    """Classify a line as 'url' or 'name' and return (input_type, cleaned_value)."""
    stripped = line.strip()
    if not stripped:
        return "name", stripped
    if stripped.lower().startswith("http://") or stripped.lower().startswith("https://"):
        return "url", stripped
    ext = tldextract.extract(stripped)
    if ext.domain and ext.suffix:
        return "url", stripped
    return "name", stripped


def _extract_domain_from_url(url: str) -> str:
    """Extract clean domain from a URL string."""
    url = url.strip().lower()
    for prefix in ("https://", "http://"):
        if url.startswith(prefix):
            url = url[len(prefix):]
            break
    if url.startswith("www."):
        url = url[4:]
    for sep in ("/", "?", "#"):
        idx = url.find(sep)
        if idx != -1:
            url = url[:idx]
    return url


def _has_meaningful_intel(extracted_data: dict) -> bool:
    """Check if extracted_data has at least one non-trivial intel field."""
    if not extracted_data:
        return False
    intel_keys = ("industry", "niche", "description", "target_market", "case_studies")
    for key in intel_keys:
        val = extracted_data.get(key)
        if val and str(val).strip():
            return True
    return False


async def update_job_progress(
    db: AsyncSession,
    job_id: uuid.UUID,
    phase: str,
    done: int,
    total: int,
    processed_rows: int | None = None,
) -> None:
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one()
    job.current_phase = phase
    job.phase_progress = {"done": done, "total": total}
    if processed_rows is not None:
        job.processed_rows = processed_rows
    await db.commit()


async def _phase_resolve_worker(
    job_id: uuid.UUID,
    total_rows: int,
    config: dict,
    queue_out: asyncio.Queue[QueueItem],
    error_event: asyncio.Event,
    progress: dict[str, int],
) -> None:
    """Phase 1: Resolve company names to domains via Serper; normalize URL inputs."""
    batch_size = settings.pipeline_batch_size

    try:
        async with AsyncSessionLocal() as db:
            for batch_start in range(0, total_rows, batch_size):
                if error_event.is_set():
                    break

                result = await db.execute(
                    select(JobResult)
                    .where(JobResult.job_id == job_id)
                    .order_by(JobResult.row_index)
                    .offset(batch_start)
                    .limit(batch_size)
                )
                batch_results = list(result.scalars().all())
                if not batch_results:
                    break

                name_rows = []
                for r in batch_results:
                    input_type = (r.input_data or {}).get("input_type", "name")
                    raw_input = (r.input_data or {}).get("input", "")

                    if input_type == "url":
                        domain = _extract_domain_from_url(raw_input)
                        r.raw_domain = domain if domain else None
                        r.status = "resolved"
                    else:
                        name_rows.append({
                            "row_index": r.row_index,
                            "company_name": raw_input,
                            "location": (r.input_data or {}).get("location", ""),
                        })

                if name_rows:
                    serper_api_key = config.get("serper_api_key") or None
                    search_outcomes = await batch_search(name_rows, api_key=serper_api_key)
                    outcome_by_idx = {int(o["row_index"]): o for o in search_outcomes}

                    result_by_row = {r.row_index: r for r in batch_results}
                    for i, row in enumerate(name_rows):
                        original_idx = row["row_index"]
                        job_result = result_by_row.get(original_idx)
                        if job_result is None:
                            continue
                        outcome = outcome_by_idx.get(i)
                        if outcome:
                            job_result.search_results = outcome.get("search_results")
                            candidate = outcome.get("candidate_domain", "")
                            job_result.raw_domain = str(candidate) if candidate else None
                        job_result.status = "resolved"

                await db.commit()

                ids = [r.id for r in batch_results]
                await queue_out.put(ids)

                done = min(batch_start + batch_size, total_rows)
                progress["resolve"] = done
                await update_job_progress(db, job_id, "resolve", done, total_rows, processed_rows=done)

    except Exception as exc:
        logger.exception("phase_resolve_worker failed: %s", exc)
        error_event.set()
        raise
    finally:
        await queue_out.put(None)


async def _phase_verify_worker(
    job_id: uuid.UUID,
    total_rows: int,
    queue_in: asyncio.Queue[QueueItem],
    queue_out: asyncio.Queue[QueueItem],
    error_event: asyncio.Event,
    progress: dict[str, int],
) -> None:
    """Phase 2: LLM-based domain verification for name-resolved rows."""
    from app.services.llm import get_llm_provider

    provider = get_llm_provider()
    verify_sem = asyncio.Semaphore(settings.verify_concurrency)

    async def _verify_batch(items: list[dict]) -> list:
        async with verify_sem:
            return await provider.verify_domains(items)

    try:
        async with AsyncSessionLocal() as db:
            total_verified = 0

            while True:
                if error_event.is_set():
                    break

                msg = await queue_in.get()
                if msg is None:
                    break

                result_ids: list[uuid.UUID] = msg

                result = await db.execute(
                    select(JobResult).where(JobResult.id.in_(result_ids))
                )
                batch_results = list(result.scalars().all())

                # Only verify name-resolved rows (URL inputs skip verification)
                needs_verify = [
                    r for r in batch_results
                    if r.raw_domain
                    and (r.input_data or {}).get("input_type") != "url"
                ]
                skip_verify = [
                    r for r in batch_results
                    if not r.raw_domain
                    or (r.input_data or {}).get("input_type") == "url"
                ]

                # Rows without a domain are already not_found
                for r in skip_verify:
                    if not r.raw_domain:
                        r.status = "not_found"

                if needs_verify:
                    all_items: list[dict] = []
                    for r in needs_verify:
                        search_results = r.search_results or {}
                        sr_list: list[dict] = []
                        if isinstance(search_results, dict):
                            raw_list = search_results.get("results", [])
                            if isinstance(raw_list, list):
                                sr_list = raw_list
                        all_items.append({
                            "row_index": r.row_index,
                            "company_name": (r.input_data or {}).get("company_name", "")
                                or (r.input_data or {}).get("input", ""),
                            "location": (r.input_data or {}).get("location", ""),
                            "candidate_domain": r.raw_domain or "",
                            "search_results": sr_list,
                        })

                    # Split into LLM batches and run in parallel
                    llm_batch_size = provider.max_batch_size
                    llm_batches = [
                        all_items[i:i + llm_batch_size]
                        for i in range(0, len(all_items), llm_batch_size)
                    ]

                    all_verification_results = await asyncio.gather(
                        *[_verify_batch(b) for b in llm_batches]
                    )

                    result_by_row_index = {r.row_index: r for r in needs_verify}

                    for vr_batch in all_verification_results:
                        for vr in vr_batch:
                            job_result = result_by_row_index.get(vr.row_index)
                            if job_result is None:
                                continue
                            job_result.verification_confidence = vr.confidence
                            if vr.match and vr.confidence >= 0.7:
                                job_result.status = "verified"
                            elif vr.suggested_domain:
                                job_result.raw_domain = vr.suggested_domain
                                job_result.status = "verified"
                            else:
                                job_result.raw_domain = None
                                job_result.status = "not_found"
                                logger.info(
                                    "Verify rejected domain for row %d: %s",
                                    vr.row_index, vr.reason,
                                )

                    await db.commit()

                total_verified += len(batch_results)
                progress["verify"] = total_verified
                await update_job_progress(db, job_id, "verify", total_verified, total_rows)

                await queue_out.put(result_ids)

    except Exception as exc:
        logger.exception("phase_verify_worker failed: %s", exc)
        error_event.set()
        raise
    finally:
        await queue_out.put(None)


async def _phase_crawl_worker(
    job_id: uuid.UUID,
    total_rows: int,
    config: dict,
    queue_in: asyncio.Queue[QueueItem],
    queue_out: asyncio.Queue[QueueItem],
    error_event: asyncio.Event,
    progress: dict[str, int],
    scraped_data: dict[str, dict[str, str]],
) -> None:
    """Phase 3: Crawl company websites using Scrape.do."""
    options = config.get("options", {})

    try:
        async with AsyncSessionLocal() as db:
            total_crawled = 0

            while True:
                if error_event.is_set():
                    break

                msg = await queue_in.get()
                if msg is None:
                    break

                result_ids: list[uuid.UUID] = msg

                result = await db.execute(
                    select(JobResult).where(JobResult.id.in_(result_ids))
                )
                batch_results = list(result.scalars().all())

                domains_to_crawl: list[str] = []
                for r in batch_results:
                    if r.raw_domain and r.raw_domain not in scraped_data:
                        if r.raw_domain not in domains_to_crawl:
                            domains_to_crawl.append(r.raw_domain)

                if domains_to_crawl:
                    crawl_results = await batch_crawl(domains_to_crawl, options)
                    scraped_data.update(crawl_results)

                for r in batch_results:
                    if r.raw_domain and r.raw_domain in scraped_data:
                        r.status = "crawled"
                        pages = scraped_data.get(r.raw_domain, {})
                        if not r.extracted_data:
                            r.extracted_data = {}
                        if options.get("homepage_raw_text"):
                            homepage_url = f"https://{r.raw_domain}"
                            homepage_text = pages.get(homepage_url, "")
                            r.extracted_data["homepage_raw_text"] = homepage_text
                        # Extract generic emails via regex (free, no LLM needed)
                        all_text = "\n".join(pages.values())
                        generic_emails = extract_generic_emails(all_text)
                        if generic_emails:
                            r.extracted_data["general_emails"] = generic_emails
                        flag_modified(r, "extracted_data")
                    elif not r.raw_domain:
                        r.status = "not_found"
                    else:
                        r.status = "scrape_failed"

                await db.commit()

                total_crawled += len(batch_results)
                progress["crawl"] = total_crawled
                await update_job_progress(db, job_id, "crawl", total_crawled, total_rows)

                await queue_out.put(result_ids)

    except Exception as exc:
        logger.exception("phase_crawl_worker failed: %s", exc)
        error_event.set()
        raise
    finally:
        await queue_out.put(None)


async def _phase_extract_worker(
    job_id: uuid.UUID,
    total_rows: int,
    config: dict,
    queue_in: asyncio.Queue[QueueItem],
    queue_out: asyncio.Queue[QueueItem],
    error_event: asyncio.Event,
    progress: dict[str, int],
    scraped_data: dict[str, dict[str, str]],
) -> None:
    """Phase 4: Extract structured intel from scraped content using LLM."""
    options = config.get("options", {})
    needs_llm = any(options.get(k) for k in ("industry_description", "target_market", "company_people"))

    try:
        async with AsyncSessionLocal() as db:
            total_extracted = 0

            while True:
                if error_event.is_set():
                    break

                msg = await queue_in.get()
                if msg is None:
                    break

                result_ids: list[uuid.UUID] = msg

                result = await db.execute(
                    select(JobResult).where(JobResult.id.in_(result_ids))
                )
                batch_results = list(result.scalars().all())

                if needs_llm:
                    # Build extraction items grouped by unique domain
                    items: list[dict] = []
                    domain_to_results: dict[str, list[JobResult]] = {}

                    for r in batch_results:
                        if r.raw_domain and r.raw_domain in scraped_data:
                            if r.raw_domain not in domain_to_results:
                                domain_to_results[r.raw_domain] = []
                                items.append({
                                    "domain": r.raw_domain,
                                    "scraped_pages": scraped_data[r.raw_domain],
                                    "options": options,
                                })
                            domain_to_results[r.raw_domain].append(r)

                    # Process LLM extraction in sub-batches of 10 to avoid DB timeout
                    _SUB_BATCH = 10
                    for sub_start in range(0, len(items), _SUB_BATCH):
                        sub_items = items[sub_start:sub_start + _SUB_BATCH]
                        logger.info("Extract sub-batch %d-%d of %d domains",
                            sub_start, sub_start + len(sub_items), len(items))

                        intel_by_domain = await batch_extract_intel(sub_items)

                        for item in sub_items:
                            domain = item["domain"]
                            intel = intel_by_domain.get(domain, {})
                            for r in domain_to_results.get(domain, []):
                                existing = r.extracted_data or {}
                                existing.update(intel)
                                r.extracted_data = existing
                                r.normalized_domain = r.raw_domain
                                if _has_meaningful_intel(r.extracted_data):
                                    r.status = "extracted"
                                else:
                                    r.status = "extract_failed"

                        # Commit after each sub-batch to keep DB connection alive
                        await db.commit()

                    # Free scraped text from memory now that LLM extraction is done
                    for domain in domain_to_results:
                        scraped_data.pop(domain, None)

                    # Mark remaining rows that didn't go through LLM
                    for r in batch_results:
                        if r.status not in ("extracted", "extract_failed", "not_found", "scrape_failed"):
                            if r.raw_domain:
                                r.normalized_domain = r.raw_domain
                                r.status = "extract_failed"
                            else:
                                r.status = "not_found"
                else:
                    for r in batch_results:
                        if r.raw_domain:
                            r.normalized_domain = r.raw_domain
                            r.status = "extracted"

                await db.commit()

                total_extracted += len(batch_results)
                progress["extract"] = total_extracted
                await update_job_progress(db, job_id, "extract", total_extracted, total_rows)

                await queue_out.put(result_ids)

    except Exception as exc:
        logger.exception("phase_extract_worker failed: %s", exc)
        error_event.set()
        raise
    finally:
        await queue_out.put(None)


async def _phase_enrich_worker(
    job_id: uuid.UUID,
    total_rows: int,
    config: dict,
    queue_in: asyncio.Queue[QueueItem],
    error_event: asyncio.Event,
    progress: dict[str, int],
    completion_event: asyncio.Event,
) -> None:
    """Phase 5: Enrich contacts via QuickEnrich API (optional)."""
    options = config.get("options", {})
    enrich_people = options.get("company_people", False)
    quickenrich_api_key = config.get("quickenrich_api_key") or None
    job_titles: list[str] = config.get("job_titles", [])
    max_contacts: int = int(config.get("max_contacts", 3))

    try:
        async with AsyncSessionLocal() as db:
            total_enriched = 0

            while True:
                if error_event.is_set():
                    break

                msg = await queue_in.get()
                if msg is None:
                    break

                result_ids: list[uuid.UUID] = msg

                if not enrich_people or not job_titles or not quickenrich_api_key:
                    total_enriched += len(result_ids)
                    progress["enrich"] = total_enriched
                    await update_job_progress(db, job_id, "enrich", total_enriched, total_rows)
                    continue

                result = await db.execute(
                    select(JobResult).where(JobResult.id.in_(result_ids))
                )
                batch_results = list(result.scalars().all())

                domains_with_rows: dict[str, list[int]] = {}
                for r in batch_results:
                    if r.normalized_domain:
                        domains_with_rows.setdefault(r.normalized_domain, []).append(r.row_index)

                if domains_with_rows:
                    contacts_by_domain = await batch_enrich(
                        domains_with_rows,
                        job_titles=job_titles,
                        max_contacts=max_contacts,
                        api_key=quickenrich_api_key,
                    )

                    result_by_row = {r.row_index: r for r in batch_results}
                    for domain, row_indices in domains_with_rows.items():
                        contacts = contacts_by_domain.get(domain, [])
                        for row_index in row_indices:
                            job_result = result_by_row.get(row_index)
                            if job_result is not None:
                                job_result.contacts = contacts
                                if contacts:
                                    job_result.status = "enriched"

                    await db.commit()

                total_enriched += len(result_ids)
                progress["enrich"] = total_enriched
                await update_job_progress(db, job_id, "enrich", total_enriched, total_rows)

    except Exception as exc:
        logger.exception("phase_enrich_worker failed: %s", exc)
        error_event.set()
        raise
    finally:
        completion_event.set()


async def _phase_deliver(job_id: uuid.UUID) -> None:
    """Phase 6: Send results email to the user."""
    async with AsyncSessionLocal() as db:
        job_result = await db.execute(select(Job).where(Job.id == job_id))
        job = job_result.scalar_one()

        result = await db.execute(
            select(JobResult).where(JobResult.job_id == job_id)
        )
        all_results = list(result.scalars().all())
        extracted_count = sum(1 for r in all_results if r.extracted_data)
        seen_contacts: set[str] = set()
        for r in all_results:
            if r.contacts:
                for c in r.contacts:
                    key = c.get("email") or f"{c.get('first_name', '')}|{c.get('last_name', '')}"
                    if key and key != "|":
                        seen_contacts.add(key)
        contacts_count = len(seen_contacts)

        email_capture_result = await db.execute(
            select(EmailCapture).where(EmailCapture.id == job.email_capture_id)
        )
        email_capture = email_capture_result.scalar_one()

        from app.auth import create_token
        download_token = create_token(email_capture.email, str(job_id))
        # Use tool-slug-aware download endpoint
        dl_slug_map = {"g2-intel": "g2", "maps-intel": "maps", "funding-intel": "funding", "people-intel": "people"}
        dl_prefix = dl_slug_map.get(job.tool_slug, "intel")
        download_url = f"{settings.backend_url}/api/v1/{dl_prefix}/download/{job_id}?token={download_token}"

        job_stats = {
            "total_rows": job.total_rows,
            "websites_found": extracted_count,
            "contacts_enriched": contacts_count,
        }

        try:
            await send_results_email(
                to_email=email_capture.email,
                download_url=download_url,
                job_stats=job_stats,
            )
        except Exception as exc:
            logger.error(
                "Email delivery failed for job_id=%s recipient=%s: %s",
                job_id, email_capture.email, exc,
            )
            # Do not fail the job — CSV is still downloadable in-app.

        await update_job_progress(db, job_id, "deliver", 1, 1)


async def run_intel_pipeline(ctx: dict, job_id: str) -> None:
    """Main entry point for company intel extraction pipeline."""
    parsed_job_id = uuid.UUID(job_id)

    async with AsyncSessionLocal() as db:
        job_result = await db.execute(select(Job).where(Job.id == parsed_job_id))
        job = job_result.scalar_one()
        total_rows = job.total_rows
        config = job.config or {}

        job.status = "resolving"
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

    # Queues: resolve → verify → crawl → extract → enrich
    queue_rv: asyncio.Queue[QueueItem] = asyncio.Queue(maxsize=5)
    queue_vc: asyncio.Queue[QueueItem] = asyncio.Queue(maxsize=5)
    queue_ce: asyncio.Queue[QueueItem] = asyncio.Queue(maxsize=5)
    queue_en: asyncio.Queue[QueueItem] = asyncio.Queue(maxsize=5)

    error_event = asyncio.Event()
    completion_event = asyncio.Event()
    progress = {"resolve": 0, "verify": 0, "crawl": 0, "extract": 0, "enrich": 0}

    scraped_data: dict[str, dict[str, str]] = {}

    tasks = [
        asyncio.create_task(
            _phase_resolve_worker(parsed_job_id, total_rows, config, queue_rv, error_event, progress),
            name="phase_resolve",
        ),
        asyncio.create_task(
            _phase_verify_worker(parsed_job_id, total_rows, queue_rv, queue_vc, error_event, progress),
            name="phase_verify",
        ),
        asyncio.create_task(
            _phase_crawl_worker(parsed_job_id, total_rows, config, queue_vc, queue_ce, error_event, progress, scraped_data),
            name="phase_crawl",
        ),
        asyncio.create_task(
            _phase_extract_worker(parsed_job_id, total_rows, config, queue_ce, queue_en, error_event, progress, scraped_data),
            name="phase_extract",
        ),
        asyncio.create_task(
            _phase_enrich_worker(parsed_job_id, total_rows, config, queue_en, error_event, progress, completion_event),
            name="phase_enrich",
        ),
    ]

    try:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                raise r

        async with AsyncSessionLocal() as db:
            job_result = await db.execute(select(Job).where(Job.id == parsed_job_id))
            job = job_result.scalar_one()
            job.status = "delivering"
            await db.commit()

        await _phase_deliver(parsed_job_id)

        async with AsyncSessionLocal() as db:
            job_result = await db.execute(select(Job).where(Job.id == parsed_job_id))
            job = job_result.scalar_one()
            job.status = "completed"
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()

        logger.info("Intel pipeline completed for job_id=%s", job_id)

    except Exception as exc:
        logger.exception("Intel pipeline failed for job_id=%s: %s", job_id, exc)
        error_event.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

        try:
            async with AsyncSessionLocal() as db:
                err_result = await db.execute(select(Job).where(Job.id == parsed_job_id))
                failed_job = err_result.scalar_one()
                failed_job.status = "failed"
                failed_job.error_message = str(exc)
                await db.commit()
        except Exception:
            logger.exception("Failed to mark intel job as failed for job_id=%s", job_id)
        raise
