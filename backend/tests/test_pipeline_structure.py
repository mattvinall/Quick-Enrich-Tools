"""Structural tests for the pipelined pipeline module."""
import inspect


def test_pipeline_has_required_functions():
    """Verify the restructured pipeline exports expected functions."""
    from app.workers import pipeline

    assert hasattr(pipeline, "run_pipeline")
    assert hasattr(pipeline, "update_job_progress")
    assert inspect.iscoroutinefunction(pipeline.run_pipeline)


def test_no_arq_worker_settings():
    """ARQ was removed (Upstash incompatibility); pipeline dispatch is now
    asyncio.create_task directly from the routers. Guard against WorkerSettings
    being re-introduced without intent."""
    from app.workers import pipeline

    assert not hasattr(pipeline, "WorkerSettings"), (
        "WorkerSettings resurfaced — if re-adopting ARQ, update the routers' "
        "dispatch paths and update this test."
    )
