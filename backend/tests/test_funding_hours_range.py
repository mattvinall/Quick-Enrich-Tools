"""Funding /discover must accept a wider range of hours values."""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


def test_discover_accepts_72_hours():
    with patch(
        "app.routers.funding.discover_funded_companies",
        new=AsyncMock(return_value=[]),
    ):
        client = TestClient(app)
        r = client.get("/api/v1/funding/discover?hours=72")
    # Should not be 422; the exact status depends on auth — assert it's NOT 422.
    assert r.status_code != 422, r.text


def test_discover_rejects_hours_over_168():
    client = TestClient(app)
    r = client.get("/api/v1/funding/discover?hours=999")
    assert r.status_code == 422
