"""ARQ worker — 5-phase pipeline for company intelligence extraction.

Phases: Resolve → Crawl → Extract → Enrich → Deliver
Uses bounded asyncio.Queue for backpressure between phases.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

import tldextract
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import EmailCapture, Job, JobResult
from app.services.email_service import send_results_email
from app.services.enrichment import batch_enrich
from app.services.scraper import batch_crawl
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
    serper_api_key = config.get("serper_api_key") or None

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
                            "location": "",
                        })

                if name_rows:
                    search_outcomes = await batch_search(
                        name_rows, api_key=serper_api_key
                    )
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
    """Phase 2: Crawl company websites using Scrape.do."""
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
                        if options.get("homepage_raw_text"):
                            pages = scraped_data.get(r.raw_domain, {})
                            homepage_url = f"https://{r.raw_domain}"
                            homepage_text = pages.get(homepage_url, "")
                            if not r.extracted_data:
                                r.extracted_data = {}
                            r.extracted_data["homepage_raw_text"] = homepage_text
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
    """Phase 3: Extract structured intel from scraped content using LLM."""
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

                    if items:
                        intel_by_domain = await batch_extract_intel(items)

                        for domain, job_results in domain_to_results.items():
                            intel = intel_by_domain.get(domain, {})
                            for r in job_results:
                                existing = r.extracted_data or {}
                                existing.update(intel)
                                r.extracted_data = existing
                                r.normalized_domain = r.raw_domain
                                r.status = "extracted"

                    for r in batch_results:
                        if r.status not in ("extracted", "not_found"):
                            if r.raw_domain:
                                r.normalized_domain = r.raw_domain
                                r.status = "extracted"
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
    """Phase 4: Enrich contacts via QuickEnrich API (optional)."""
    options = config.get("options", {})
    enrich_people = options.get("company_people", False)
    quickenrich_api_key = config.get("quickenrich_api_key") or None

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

                if not enrich_people or not quickenrich_api_key:
                    total_enriched += len(result_ids)
                    progress["enrich"] = total_enriched
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
                    job_titles = ["CEO", "Founder", "Owner", "President", "Managing Director"]

                    contacts_by_domain = await batch_enrich(
                        domains_with_rows,
                        job_titles=job_titles,
                        max_contacts=5,
                        api_key=quickenrich_api_key,
                    )

                    result_by_row = {r.row_index: r for r in batch_results}
                    for domain, row_indices in domains_with_rows.items():
                        contacts = contacts_by_domain.get(domain, [])
                        for row_index in row_indices:
                            job_result = result_by_row.get(row_index)
                            if job_result is not None:
                                job_result.contacts = contacts
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
    """Phase 5: Send results email to the user."""
    async with AsyncSessionLocal() as db:
        job_result = await db.execute(select(Job).where(Job.id == job_id))
        job = job_result.scalar_one()

        result = await db.execute(
            select(JobResult).where(JobResult.job_id == job_id)
        )
        all_results = list(result.scalars().all())
        extracted_count = sum(1 for r in all_results if r.extracted_data)
        contacts_count = sum(1 for r in all_results if r.contacts and len(r.contacts) > 0)

        email_capture_result = await db.execute(
            select(EmailCapture).where(EmailCapture.id == job.email_capture_id)
        )
        email_capture = email_capture_result.scalar_one()

        from app.auth import create_token
        download_token = create_token(email_capture.email, str(job_id))
        download_url = f"{settings.backend_url}/api/v1/intel/download/{job_id}?token={download_token}"

        job_stats = {
            "total_rows": job.total_rows,
            "websites_found": extracted_count,
            "contacts_enriched": contacts_count,
        }

        try:
            send_results_email(
                to_email=email_capture.email,
                download_url=download_url,
                job_stats=job_stats,
            )
        except Exception:
            logger.exception("Failed to send intel results email for job_id=%s", job_id)

        await update_job_progress(db, job_id, "deliver", 1, 1)


async def run_intel_pipeline(ctx: dict, job_id: str) -> None:
    """Main ARQ entry point for company intel extraction pipeline."""
    parsed_job_id = uuid.UUID(job_id)

    async with AsyncSessionLocal() as db:
        job_result = await db.execute(select(Job).where(Job.id == parsed_job_id))
        job = job_result.scalar_one()
        total_rows = job.total_rows
        config = job.config or {}

        job.status = "resolving"
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

    queue_rc: asyncio.Queue[QueueItem] = asyncio.Queue(maxsize=5)
    queue_ce: asyncio.Queue[QueueItem] = asyncio.Queue(maxsize=5)
    queue_en: asyncio.Queue[QueueItem] = asyncio.Queue(maxsize=5)

    error_event = asyncio.Event()
    completion_event = asyncio.Event()
    progress = {"resolve": 0, "crawl": 0, "extract": 0, "enrich": 0}

    scraped_data: dict[str, dict[str, str]] = {}

    tasks = [
        asyncio.create_task(
            _phase_resolve_worker(parsed_job_id, total_rows, config, queue_rc, error_event, progress),
            name="phase_resolve",
        ),
        asyncio.create_task(
            _phase_crawl_worker(parsed_job_id, total_rows, config, queue_rc, queue_ce, error_event, progress, scraped_data),
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
