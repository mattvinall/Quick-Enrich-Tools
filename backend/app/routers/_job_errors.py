"""Shared helpers for surfacing background-task failures to the UI.

All pipelines dispatch via `asyncio.create_task(run_*_pipeline(...))` and attach
a done-callback. If the pipeline raises, we need to persist the error to the
Job row so the SSE/polling layer can show it instead of leaving the UI stuck
at "Connecting...". This helper centralises that write with a two-phase retry
that survives CheckViolation-class errors on the status column.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import Job

logger = logging.getLogger(__name__)

# Hold strong references to fire-and-forget error-persistence tasks so the GC
# can't reap them mid-flight. Tasks self-remove on completion.
_pending_failure_writes: set[asyncio.Task] = set()


async def mark_job_failed(job_id: uuid.UUID, exc: BaseException) -> None:
    """Set Job.status='failed' and record the error so the UI can surface it.

    Two-phase write: if the combined status+error_message commit fails (e.g. the
    original crash was a CheckViolation on the status column), retry writing
    only error_message so the UI still shows something useful instead of hanging.
    """
    message = f"Pipeline crashed: {type(exc).__name__}: {exc}"
    try:
        async with AsyncSessionLocal() as db:
            job_result = await db.execute(select(Job).where(Job.id == job_id))
            job = job_result.scalar_one_or_none()
            if job is None:
                return
            job.status = "failed"
            job.error_message = message
            await db.commit()
        return
    except Exception as inner:
        logger.error(
            "Failed to mark job %s status=failed after pipeline error: %s",
            job_id, inner,
        )

    try:
        async with AsyncSessionLocal() as db:
            job_result = await db.execute(select(Job).where(Job.id == job_id))
            job = job_result.scalar_one_or_none()
            if job is None:
                return
            job.error_message = message
            await db.commit()
    except Exception as inner2:
        logger.error(
            "Fallback error_message write also failed for job %s: %s",
            job_id, inner2,
        )


def make_failure_callback(
    job_id: uuid.UUID,
    logger_: logging.Logger,
    label: str = "Pipeline",
):
    """Build an `add_done_callback` handler that persists pipeline crashes."""

    def _on_done(t: asyncio.Task) -> None:
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            logger_.error("%s failed for job %s: %s", label, job_id, exc)
            failure_task = asyncio.create_task(mark_job_failed(job_id, exc))
            _pending_failure_writes.add(failure_task)
            failure_task.add_done_callback(_pending_failure_writes.discard)

    return _on_done
