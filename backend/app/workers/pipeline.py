"""ARQ worker that orchestrates the 5-phase processing pipeline."""

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


async def phase_search(
    db: AsyncSession,
    job_id: uuid.UUID,
    results: list[JobResult],
) -> None:
    """Phase 1: Search for candidate domains via Serper."""
    total = len(results)
    batch_size = settings.search_batch_size

    for batch_start in range(0, total, batch_size):
        batch = results[batch_start : batch_start + batch_size]

        rows = [
            {
                "row_index": r.row_index,
                "company_name": r.input_data.get("company_name", ""),
                "location": r.input_data.get("location", ""),
            }
            for r in batch
        ]

        search_outcomes = await batch_search(rows)

        # Index results by row_index within this batch
        outcome_by_row: dict[int, dict[str, object]] = {
            int(o["row_index"]): o for o in search_outcomes
        }

        # Map outcomes back using the original row_index on each JobResult
        result_by_row_index: dict[int, JobResult] = {r.row_index: r for r in batch}

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

        done = min(batch_start + batch_size, total)
        await update_job_progress(db, job_id, "search", done, total, processed_rows=done)


async def phase_verify(
    db: AsyncSession,
    job_id: uuid.UUID,
    results: list[JobResult],
) -> None:
    """Phase 2: LLM-based domain verification."""
    provider = get_llm_provider()

    with_domain = [r for r in results if r.raw_domain]
    without_domain = [r for r in results if not r.raw_domain]

    # Mark rows with no raw_domain as not_found immediately
    for r in without_domain:
        r.status = "not_found"
    if without_domain:
        await db.commit()

    total = len(with_domain)
    batch_size = provider.max_batch_size
    done = 0

    for batch_start in range(0, total, batch_size):
        batch = with_domain[batch_start : batch_start + batch_size]

        items: list[dict[str, object]] = []
        for r in batch:
            search_results = r.search_results or {}
            first_result: dict[str, object] = {}
            if isinstance(search_results, dict):
                sr_list = search_results.get("results", [])
                if isinstance(sr_list, list) and sr_list:
                    first_result = sr_list[0]

            items.append(
                {
                    "row_index": r.row_index,
                    "company_name": r.input_data.get("company_name", ""),
                    "location": r.input_data.get("location", ""),
                    "candidate_domain": r.raw_domain or "",
                    "search_snippet": str(first_result.get("snippet", "")),
                }
            )

        verification_results = await provider.verify_domains(items)

        result_by_row_index: dict[int, JobResult] = {r.row_index: r for r in batch}

        for vr in verification_results:
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

        done = min(batch_start + batch_size, total)
        await update_job_progress(db, job_id, "verify", done, total)


async def phase_normalize(
    db: AsyncSession,
    job_id: uuid.UUID,
    results: list[JobResult],
) -> None:
    """Phase 3: Normalize and resolve verified domains."""
    eligible = [r for r in results if r.verified_domain]
    total = len(eligible)
    batch_size = settings.normalize_batch_size
    done = 0

    for batch_start in range(0, total, batch_size):
        batch = eligible[batch_start : batch_start + batch_size]

        rows: list[dict[str, str | None]] = [
            {"verified_domain": r.verified_domain} for r in batch
        ]

        normalize_outcomes = await batch_normalize(
            rows,
            resolve_redirects=True,
            concurrency=settings.normalize_concurrency,
        )

        # batch_normalize uses enumerate index, so outcome row_index maps to batch position
        outcome_by_batch_pos: dict[int, dict[str, str | bool | int | None]] = {
            int(o["row_index"]): o for o in normalize_outcomes
        }

        for batch_pos, job_result in enumerate(batch):
            outcome = outcome_by_batch_pos.get(batch_pos)
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

        done = min(batch_start + batch_size, total)
        await update_job_progress(db, job_id, "normalize", done, total)


async def phase_enrich(
    db: AsyncSession,
    job_id: uuid.UUID,
    results: list[JobResult],
    config: dict[str, object],
) -> None:
    """Phase 4: Contact enrichment grouped by normalized domain."""
    if not config.get("enrich_contacts"):
        return

    job_titles: list[str] = config.get("job_titles", [])  # type: ignore[assignment]
    if not job_titles:
        return

    max_contacts: int = int(config.get("max_contacts", 1))

    # Group row indices by normalized_domain
    domains_with_rows: dict[str, list[int]] = {}
    for r in results:
        if r.normalized_domain:
            domains_with_rows.setdefault(r.normalized_domain, []).append(r.row_index)

    if not domains_with_rows:
        return

    contacts_by_domain = await batch_enrich(
        domains_with_rows,
        job_titles=job_titles,
        max_contacts=max_contacts,
    )

    # Map contacts back to all rows sharing that domain
    result_by_row_index: dict[int, JobResult] = {r.row_index: r for r in results}

    for domain, row_indices in domains_with_rows.items():
        contacts = contacts_by_domain.get(domain, [])
        for row_index in row_indices:
            job_result = result_by_row_index.get(row_index)
            if job_result is not None:
                job_result.contacts = contacts  # type: ignore[assignment]
                job_result.status = "enriched"

    await db.commit()

    total = len(domains_with_rows)
    await update_job_progress(db, job_id, "enrich", total, total)


async def phase_deliver(
    db: AsyncSession,
    job_id: uuid.UUID,
    job: Job,
) -> None:
    """Phase 5: Send results email to the user."""
    result = await db.execute(
        select(JobResult).where(JobResult.job_id == job_id)
    )
    all_results = list(result.scalars().all())

    found = sum(1 for r in all_results if r.normalized_domain)

    email_capture_result = await db.execute(
        select(EmailCapture).where(EmailCapture.id == job.email_capture_id)
    )
    email_capture = email_capture_result.scalar_one()

    download_url = f"{settings.frontend_url}/jobs/{job_id}/download"

    job_stats: dict[str, int] = {
        "total_rows": job.total_rows,
        "websites_found": found,
    }

    try:
        send_results_email(
            to_email=email_capture.email,
            download_url=download_url,
            job_stats=job_stats,
        )
    except Exception as e:
        logger.warning("Failed to send results email for job_id=%s: %s", job_id, e)

    await update_job_progress(db, job_id, "deliver", 1, 1)


async def run_pipeline(ctx: dict[str, object], job_id: str) -> None:
    """Main ARQ entry point — orchestrates all 5 pipeline phases."""
    parsed_job_id = uuid.UUID(job_id)

    async with AsyncSessionLocal() as db:
        try:
            job_result = await db.execute(select(Job).where(Job.id == parsed_job_id))
            job = job_result.scalar_one()

            results_result = await db.execute(
                select(JobResult).where(JobResult.job_id == parsed_job_id).order_by(JobResult.row_index)
            )
            results = list(results_result.scalars().all())

            job.status = "searching"
            job.started_at = datetime.now(timezone.utc)
            await db.commit()

            config: dict[str, object] = job.config or {}

            await phase_search(db, parsed_job_id, results)

            job_result2 = await db.execute(select(Job).where(Job.id == parsed_job_id))
            job = job_result2.scalar_one()
            job.status = "verifying"
            await db.commit()

            await phase_verify(db, parsed_job_id, results)

            job_result3 = await db.execute(select(Job).where(Job.id == parsed_job_id))
            job = job_result3.scalar_one()
            job.status = "normalizing"
            await db.commit()

            await phase_normalize(db, parsed_job_id, results)

            job_result4 = await db.execute(select(Job).where(Job.id == parsed_job_id))
            job = job_result4.scalar_one()
            job.status = "enriching"
            await db.commit()

            await phase_enrich(db, parsed_job_id, results, config)

            job_result5 = await db.execute(select(Job).where(Job.id == parsed_job_id))
            job = job_result5.scalar_one()
            job.status = "delivering"
            await db.commit()

            await phase_deliver(db, parsed_job_id, job)

            job_result6 = await db.execute(select(Job).where(Job.id == parsed_job_id))
            job = job_result6.scalar_one()
            job.status = "completed"
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()

            logger.info("Pipeline completed for job_id=%s", job_id)

        except Exception as exc:
            logger.exception("Pipeline failed for job_id=%s: %s", job_id, exc)
            try:
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
