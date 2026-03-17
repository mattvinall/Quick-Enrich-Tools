"""Tests for config settings."""
from app.config import Settings


def test_default_settings_have_pipeline_fields():
    """Verify new pipeline settings exist with correct defaults."""
    s = Settings(
        database_url="postgresql+asyncpg://localhost/test",
        redis_url="redis://localhost",
    )
    assert s.verify_concurrency == 5
    assert s.pipeline_batch_size == 200
    assert s.serper_concurrency == 50
    assert s.enrich_concurrency == 30
    # Removed settings should not exist
    assert not hasattr(s, "llm_concurrency")
    assert not hasattr(s, "search_batch_size")
