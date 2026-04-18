"""Accounting tests for the intel pipeline enrich phase.

Regression tests for H3: the enrich phase previously incremented
``total_enriched`` by ``len(result_ids)`` unconditionally, which inflated
the user-visible ``contacts_enriched`` stat whenever rows skipped the
QuickEnrich API call (no API key, no job_titles, no normalized_domain).

These tests pin the correct behaviour: only rows whose row-level
``status`` is ``"enriched"`` after the batch should contribute to the
counter.
"""
from types import SimpleNamespace


def test_count_enriched_in_batch_exists():
    """Helper must be exported so it can be unit-tested and reused."""
    from app.workers import intel_pipeline

    assert hasattr(intel_pipeline, "_count_enriched_in_batch")


def test_count_enriched_in_batch_no_enriched_rows():
    """A batch where NO row has status='enriched' must count 0.

    This is the scenario H3 fixes: the batch ran through the enrich
    phase but nothing actually produced contacts (e.g. no
    normalized_domain on any row, or the API returned no contacts).
    """
    from app.workers.intel_pipeline import _count_enriched_in_batch

    batch = [
        SimpleNamespace(status="extract_failed"),
        SimpleNamespace(status="not_found"),
        SimpleNamespace(status="extracted"),  # extracted but no contacts
        SimpleNamespace(status="scrape_failed"),
    ]
    assert _count_enriched_in_batch(batch) == 0


def test_count_enriched_in_batch_mixed():
    """Only rows with status='enriched' should be counted."""
    from app.workers.intel_pipeline import _count_enriched_in_batch

    batch = [
        SimpleNamespace(status="enriched"),
        SimpleNamespace(status="extracted"),
        SimpleNamespace(status="enriched"),
        SimpleNamespace(status="not_found"),
    ]
    assert _count_enriched_in_batch(batch) == 2


def test_count_enriched_in_batch_empty():
    from app.workers.intel_pipeline import _count_enriched_in_batch

    assert _count_enriched_in_batch([]) == 0


def test_count_enriched_in_batch_all_enriched():
    from app.workers.intel_pipeline import _count_enriched_in_batch

    batch = [SimpleNamespace(status="enriched") for _ in range(5)]
    assert _count_enriched_in_batch(batch) == 5


def test_enrich_phase_uses_helper_not_len_result_ids():
    """Source-level guard: the enrich phase must use the helper on
    ``batch_results`` rather than incrementing by ``len(result_ids)``
    after the ``db.commit()`` that persists contact updates.

    This is a regression guard against the specific bug pattern the
    task was written to fix.
    """
    import inspect

    from app.workers import intel_pipeline

    src = inspect.getsource(intel_pipeline._phase_enrich_worker)

    # The fix uses the helper to count only rows whose status is
    # 'enriched' after the commit.
    assert "_count_enriched_in_batch(batch_results)" in src, (
        "Expected _phase_enrich_worker to increment total_enriched via "
        "_count_enriched_in_batch(batch_results). Did the H3 fix regress?"
    )

    # The post-commit path must no longer do `total_enriched += len(result_ids)`.
    # Find the occurrence after the 'await db.commit()' that persists contacts.
    commit_idx = src.find("await db.commit()")
    assert commit_idx != -1
    tail = src[commit_idx:]
    assert "total_enriched += len(result_ids)" not in tail, (
        "Unconditional len(result_ids) accumulator still present after "
        "db.commit(); H3 regression."
    )
