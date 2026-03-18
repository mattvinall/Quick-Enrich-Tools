"""ARQ worker — queue-based pipelined processing pipeline.

Phases run concurrently via asyncio.Queue. Each phase has its own DB
session. Queues pass lists of JobResult primary keys (UUIDs) between
phases to avoid ORM staleness.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from arq.connections import RedisSettings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import EmailCapture, Job, JobResult
from app.services.email_service import send_results_email
from app.services.enrichment import batch_enrich
from app.services.llm import get_llm_provider
from app.services.normalizer import batch_normalize
from app.services.serper import batch_search

logger = logging.getLogger(__name__)

# Type alias for items flowing through queues: lists of JobResult UUIDs
QueueItem = list[uuid.UUID] | None  # None = sentinel to shut down


async def update_job_progress(
    db: AsyncSession,
    job_id: uuid.UUID,
    phase: str,
    done: int,
    total: int,
    processed_rows: int | None = None,
) -> None:
    """Update job's current_phase, phase_progress JSONB, and optionally processed_rows."""
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one()
    job.current_phase = phase
    job.phase_progress = {"done": done, "total": total}
    if processed_rows is not None:
        job.processed_rows = processed_rows
    await db.commit()


# ---------------------------------------------------------------------------
# Phase workers — each runs in its own async task with its own DB session
# ---------------------------------------------------------------------------


async def _phase_search_worker(
    job_id: uuid.UUID,
    total_rows: int,
    queue_out: asyncio.Queue[QueueItem],
    error_event: asyncio.Event,
    progress: dict[str, int],
) -> None:
    """Phase 1: Search for candidate domains via Serper."""
    batch_size = settings.pipeline_batch_size

    try:
        async with AsyncSessionLocal() as db:
            for batch_start in range(0, total_rows, batch_size):
                if error_event.is_set():
                    break

                # Load micro-batch of JobResults from DB
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

                rows = [
                    {
                        "row_index": r.row_index,
                        "company_name": r.input_data.get("company_name", ""),
                        "location": r.input_data.get("location", ""),
                    }
                    for r in batch_results
                ]

                search_outcomes = await batch_search(rows)

                outcome_by_row: dict[int, dict[str, object]] = {
                    int(o["row_index"]): o for o in search_outcomes
                }

                result_by_row_index = {r.row_index: r for r in batch_results}

                for idx_in_batch, row in enumerate(rows):
                    original_row_index = row["row_index"]
                    job_result = result_by_row_index[original_row_index]
                    outcome = outcome_by_row.get(idx_in_batch)
                    if outcome is not None:
                        job_result.search_results = outcome.get("search_results")
                        candidate = outcome.get("candidate_domain", "")
                        job_result.raw_domain = str(candidate) if candidate else None
                    job_result.status = "searched"

                await db.commit()

                # Push IDs to next phase
                ids = [r.id for r in batch_results]
                await queue_out.put(ids)

                done = min(batch_start + batch_size, total_rows)
                progress["search"] = done
                await update_job_progress(db, job_id, "search", done, total_rows, processed_rows=done)

    except Exception as exc:
        logger.exception("phase_search_worker failed: %s", exc)
        error_event.set()
        raise
    finally:
        await queue_out.put(None)  # Sentinel


async def _phase_verify_worker(
    job_id: uuid.UUID,
    total_rows: int,
    queue_in: asyncio.Queue[QueueItem],
    queue_out: asyncio.Queue[QueueItem],
    error_event: asyncio.Event,
    progress: dict[str, int],
) -> None:
    """Phase 2: LLM-based domain verification with parallel batches."""
    provider = get_llm_provider()
    verify_sem = asyncio.Semaphore(settings.verify_concurrency)

    async def _verify_batch(items: list[dict[str, object]]) -> list:
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

                # Load fresh from DB
                result = await db.execute(
                    select(JobResult).where(JobResult.id.in_(result_ids))
                )
                batch_results = list(result.scalars().all())

                with_domain = [r for r in batch_results if r.raw_domain]
                without_domain = [r for r in batch_results if not r.raw_domain]

                for r in without_domain:
                    r.status = "not_found"
                if without_domain:
                    await db.commit()

                if with_domain:
                    # Build LLM items
                    all_items: list[dict[str, object]] = []
                    for r in with_domain:
                        search_results = r.search_results or {}
                        first_result: dict[str, object] = {}
                        if isinstance(search_results, dict):
                            sr_list = search_results.get("results", [])
                            if isinstance(sr_list, list) and sr_list:
                                first_result = sr_list[0]
                        all_items.append(
                            {
                                "row_index": r.row_index,
                                "company_name": r.input_data.get("company_name", ""),
                                "location": r.input_data.get("location", ""),
                                "candidate_domain": r.raw_domain or "",
                                "search_snippet": str(first_result.get("snippet", "")),
                            }
                        )

                    # Split into LLM batches and run in parallel
                    llm_batch_size = provider.max_batch_size
                    llm_batches = [
                        all_items[i : i + llm_batch_size]
                        for i in range(0, len(all_items), llm_batch_size)
                    ]

                    all_verification_results = await asyncio.gather(
                        *[_verify_batch(b) for b in llm_batches]
                    )

                    result_by_row_index = {r.row_index: r for r in with_domain}

                    for vr_batch in all_verification_results:
                        for vr in vr_batch:
                            job_result = result_by_row_index.get(vr.row_index)
                            if job_result is None:
                                continue
                            job_result.verification_confidence = vr.confidence
                            if vr.match and vr.confidence >= 0.7:
                                job_result.verified_domain = job_result.raw_domain
                                job_result.status = "verified"
                            elif vr.suggested_domain:
                                job_result.verified_domain = vr.suggested_domain
                                job_result.status = "verified"
                            else:
                                job_result.status = "not_found"

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


async def _phase_normalize_worker(
    job_id: uuid.UUID,
    total_rows: int,
    queue_in: asyncio.Queue[QueueItem],
    queue_out: asyncio.Queue[QueueItem],
    error_event: asyncio.Event,
    progress: dict[str, int],
) -> None:
    """Phase 3: Normalize and resolve verified domains."""
    try:
        async with AsyncSessionLocal() as db:
            total_normalized = 0

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

                eligible = [r for r in batch_results if r.verified_domain]

                if eligible:
                    rows = [{"verified_domain": r.verified_domain} for r in eligible]

                    normalize_outcomes = await batch_normalize(
                        rows,
                        resolve_redirects=True,
                        concurrency=settings.normalize_concurrency,
                    )

                    outcome_by_pos = {int(o["row_index"]): o for o in normalize_outcomes}

                    for batch_pos, job_result in enumerate(eligible):
                        outcome = outcome_by_pos.get(batch_pos)
                        if outcome is None:
                            job_result.status = "failed"
                            continue
                        if outcome.get("blocked"):
                            job_result.status = "blocked"
                        elif outcome.get("error") or not outcome.get("domain"):
                            job_result.status = "failed"
                        else:
                            job_result.normalized_domain = str(outcome["domain"])
                            job_result.status = "normalized"

                    await db.commit()

                total_normalized += len(batch_results)
                progress["normalize"] = total_normalized
                await update_job_progress(db, job_id, "normalize", total_normalized, total_rows)

                await queue_out.put(result_ids)

    except Exception as exc:
        logger.exception("phase_normalize_worker failed: %s", exc)
        error_event.set()
        raise
    finally:
        await queue_out.put(None)


async def _phase_enrich_worker(
    job_id: uuid.UUID,
    total_rows: int,
    config: dict[str, object],
    queue_in: asyncio.Queue[QueueItem],
    error_event: asyncio.Event,
    progress: dict[str, int],
    completion_event: asyncio.Event,
) -> None:
    """Phase 4: Contact enrichment grouped by normalized domain."""
    enrich_contacts = config.get("enrich_contacts", False)
    job_titles: list[str] = config.get("job_titles", [])  # type: ignore[assignment]
    max_contacts: int = int(config.get("max_contacts", 1))

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

                if not enrich_contacts or not job_titles:
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
                    contacts_by_domain = await batch_enrich(
                        domains_with_rows,
                        job_titles=job_titles,
                        max_contacts=max_contacts,
                    )

                    result_by_row_index = {r.row_index: r for r in batch_results}
                    for domain, row_indices in domains_with_rows.items():
                        contacts = contacts_by_domain.get(domain, [])
                        for row_index in row_indices:
                            job_result = result_by_row_index.get(row_index)
                            if job_result is not None:
                                job_result.contacts = contacts  # type: ignore[assignment]
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


async def _phase_deliver(
    job_id: uuid.UUID,
) -> None:
    """Phase 5: Send results email to the user."""
    async with AsyncSessionLocal() as db:
        job_result = await db.execute(select(Job).where(Job.id == job_id))
        job = job_result.scalar_one()

        result = await db.execute(
            select(JobResult).where(JobResult.job_id == job_id)
        )
        all_results = list(result.scalars().all())
        found = sum(1 for r in all_results if r.normalized_domain)
        contacts_enriched = sum(
            1 for r in all_results if r.contacts and len(r.contacts) > 0
        )

        email_capture_result = await db.execute(
            select(EmailCapture).where(EmailCapture.id == job.email_capture_id)
        )
        email_capture = email_capture_result.scalar_one()

        # Build a JWT-authenticated download URL pointing to the backend API
        from app.auth import create_token
        download_token = create_token(email_capture.email, str(job_id))
        download_url = f"{settings.backend_url}/api/v1/download/{job_id}?token={download_token}"
        job_stats: dict[str, int] = {
            "total_rows": job.total_rows,
            "websites_found": found,
            "contacts_enriched": contacts_enriched,
        }

        try:
            send_results_email(
                to_email=email_capture.email,
                download_url=download_url,
                job_stats=job_stats,
            )
            logger.info("Results email sent successfully for job_id=%s to=%s", job_id, email_capture.email)
        except Exception:
            logger.exception("Failed to send results email for job_id=%s to=%s", job_id, email_capture.email)

        await update_job_progress(db, job_id, "deliver", 1, 1)


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


async def run_pipeline(ctx: dict[str, object], job_id: str) -> None:
    """Main ARQ entry point — orchestrates the pipelined processing pipeline."""
    parsed_job_id = uuid.UUID(job_id)

    # Read job metadata with a short-lived session
    async with AsyncSessionLocal() as db:
        job_result = await db.execute(select(Job).where(Job.id == parsed_job_id))
        job = job_result.scalar_one()
        total_rows = job.total_rows
        config: dict[str, object] = job.config or {}

        job.status = "searching"
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

    # Bounded queues for backpressure between phases
    queue_sv: asyncio.Queue[QueueItem] = asyncio.Queue(maxsize=5)  # search -> verify
    queue_vn: asyncio.Queue[QueueItem] = asyncio.Queue(maxsize=5)  # verify -> normalize
    queue_ne: asyncio.Queue[QueueItem] = asyncio.Queue(maxsize=5)  # normalize -> enrich

    error_event = asyncio.Event()
    completion_event = asyncio.Event()
    progress: dict[str, int] = {"search": 0, "verify": 0, "normalize": 0, "enrich": 0}

    # Launch all phase workers concurrently
    tasks = [
        asyncio.create_task(
            _phase_search_worker(parsed_job_id, total_rows, queue_sv, error_event, progress),
            name="phase_search",
        ),
        asyncio.create_task(
            _phase_verify_worker(parsed_job_id, total_rows, queue_sv, queue_vn, error_event, progress),
            name="phase_verify",
        ),
        asyncio.create_task(
            _phase_normalize_worker(parsed_job_id, total_rows, queue_vn, queue_ne, error_event, progress),
            name="phase_normalize",
        ),
        asyncio.create_task(
            _phase_enrich_worker(parsed_job_id, total_rows, config, queue_ne, error_event, progress, completion_event),
            name="phase_enrich",
        ),
    ]

    try:
        # Wait for all phase tasks to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check for errors
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                raise result

        # Phase 5: Deliver (runs after all pipeline phases complete)
        async with AsyncSessionLocal() as db:
            job_result = await db.execute(select(Job).where(Job.id == parsed_job_id))
            job = job_result.scalar_one()
            job.status = "delivering"
            await db.commit()

        await _phase_deliver(parsed_job_id)

        # Mark job as completed
        async with AsyncSessionLocal() as db:
            job_result = await db.execute(select(Job).where(Job.id == parsed_job_id))
            job = job_result.scalar_one()
            job.status = "completed"
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()

        logger.info("Pipeline completed for job_id=%s", job_id)

    except Exception as exc:
        logger.exception("Pipeline failed for job_id=%s: %s", job_id, exc)
        error_event.set()

        # Cancel any still-running tasks
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
            logger.exception("Failed to mark job as failed for job_id=%s", job_id)
        raise


def _parse_redis_settings(redis_url: str) -> RedisSettings:
    """Parse a redis:// or rediss:// URL into an arq RedisSettings instance."""
    from urllib.parse import urlparse

    parsed = urlparse(redis_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 6379
    password = parsed.password or None
    db_index = int(parsed.path.lstrip("/")) if parsed.path and parsed.path != "/" else 0
    use_ssl = parsed.scheme == "rediss"

    return RedisSettings(host=host, port=port, password=password, database=db_index, ssl=use_ssl)


class WorkerSettings:
    functions = [run_pipeline]
    redis_settings = _parse_redis_settings(settings.redis_url)
    max_jobs = 5
    job_timeout = 7200
