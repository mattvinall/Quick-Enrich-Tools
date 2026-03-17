"""Structural tests for the pipelined pipeline module."""
import inspect


def test_pipeline_has_required_functions():
    """Verify the restructured pipeline exports expected functions."""
    from app.workers import pipeline

    assert hasattr(pipeline, "run_pipeline")
    assert hasattr(pipeline, "update_job_progress")
    assert inspect.iscoroutinefunction(pipeline.run_pipeline)


def test_worker_settings_exist():
    """WorkerSettings must still be importable for ARQ."""
    from app.workers.pipeline import WorkerSettings

    assert hasattr(WorkerSettings, "functions")
    assert hasattr(WorkerSettings, "max_jobs")
    assert WorkerSettings.max_jobs == 5
