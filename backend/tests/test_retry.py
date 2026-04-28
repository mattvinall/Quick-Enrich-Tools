"""Tests for async retry utility."""
import pytest
import httpx

from app.services.retry import retry_async


class FakeResponse:
    def __init__(self, status_code: int, headers: dict[str, str] | None = None):
        self.status_code = status_code
        self.request = httpx.Request("GET", "https://example.com")
        self.headers = headers or {}


@pytest.mark.asyncio
async def test_retry_succeeds_on_first_try():
    call_count = 0

    async def fn():
        nonlocal call_count
        call_count += 1
        return "ok"

    result = await retry_async(fn)
    assert result == "ok"
    assert call_count == 1


@pytest.mark.asyncio
async def test_retry_retries_on_429_then_succeeds():
    call_count = 0

    async def fn():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            resp = FakeResponse(429)
            raise httpx.HTTPStatusError("rate limited", request=resp.request, response=resp)
        return "ok"

    result = await retry_async(fn, max_retries=3, base_delay=0.01)
    assert result == "ok"
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_raises_on_non_retryable():
    async def fn():
        resp = FakeResponse(400)
        raise httpx.HTTPStatusError("bad request", request=resp.request, response=resp)

    with pytest.raises(httpx.HTTPStatusError):
        await retry_async(fn, max_retries=3, base_delay=0.01)


@pytest.mark.asyncio
async def test_retry_retries_custom_exceptions():
    call_count = 0

    class CustomError(Exception):
        pass

    async def fn():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise CustomError("transient")
        return "ok"

    result = await retry_async(
        fn, max_retries=3, base_delay=0.01, retryable_exceptions=(CustomError,)
    )
    assert result == "ok"
    assert call_count == 2


@pytest.mark.asyncio
async def test_retry_exhausts_retries():
    async def fn():
        resp = FakeResponse(429)
        raise httpx.HTTPStatusError("rate limited", request=resp.request, response=resp)

    with pytest.raises(httpx.HTTPStatusError):
        await retry_async(fn, max_retries=2, base_delay=0.01)


@pytest.mark.asyncio
async def test_retry_honors_retry_after_seconds(monkeypatch):
    """A numeric Retry-After header should drive the sleep duration."""
    sleeps: list[float] = []

    async def fake_sleep(d: float) -> None:
        sleeps.append(d)

    monkeypatch.setattr("app.services.retry.asyncio.sleep", fake_sleep)

    call_count = 0

    async def fn():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            resp = FakeResponse(429, headers={"retry-after": "2"})
            raise httpx.HTTPStatusError("rate limited", request=resp.request, response=resp)
        return "ok"

    result = await retry_async(fn, max_retries=3, base_delay=0.01, max_delay=10.0)
    assert result == "ok"
    assert sleeps == [2.0]


@pytest.mark.asyncio
async def test_retry_caps_retry_after_at_max_delay(monkeypatch):
    """A wildly-large Retry-After should be clamped to max_delay."""
    sleeps: list[float] = []

    async def fake_sleep(d: float) -> None:
        sleeps.append(d)

    monkeypatch.setattr("app.services.retry.asyncio.sleep", fake_sleep)

    call_count = 0

    async def fn():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            resp = FakeResponse(429, headers={"retry-after": "9999"})
            raise httpx.HTTPStatusError("rate limited", request=resp.request, response=resp)
        return "ok"

    await retry_async(fn, max_retries=3, base_delay=0.01, max_delay=5.0)
    assert sleeps == [5.0]
