from collections import deque

import pytest

import ibproxy.rate as ratemod
from ibproxy.rate import limit as limitmod
from ibproxy.rate.limit import LeakyBucket, enforce_rate_limit


@pytest.fixture(autouse=True)
def _clear_times():
    # Ensure a clean state for each test
    ratemod.times.clear()
    yield
    ratemod.times.clear()


def test_latest_when_no_requests_returns_none():
    # No entries at all
    assert ratemod.latest() is None
    # Specific endpoint also None
    assert ratemod.latest("/no-such-endpoint") is None


def test_latest_for_endpoint_returns_last_timestamp():
    # populate a single endpoint with a few timestamps
    ratemod.times["/a"] = deque([1.0, 2.5, 3.2])
    assert ratemod.latest("/a") == 3.2

    # endpoint with single value
    ratemod.times["/b"] = deque([10.0])
    assert ratemod.latest("/b") == 10.0


def test_latest_overall_returns_max_of_endpoint_tails():
    # multiple endpoints with different last timestamps
    ratemod.times["/a"] = deque([1.0, 2.0])
    ratemod.times["/b"] = deque([5.5])
    ratemod.times["/c"] = deque([3.3, 4.4, 4.9])

    # overall latest should be the maximum of the last entries: max(2.0, 5.5, 4.9) == 5.5
    assert ratemod.latest() == 5.5


def test_latest_ignores_empty_deques_in_overall():
    # Create some endpoints; one is empty
    ratemod.times["/a"] = deque([1.0, 2.0])
    ratemod.times["empty"] = deque()  # explicitly empty
    # overall should still return 2.0 and not fail due to the empty deque
    assert ratemod.latest() == 2.0


@pytest.mark.asyncio
async def test_leaky_bucket_acquire_returns_token_when_available():
    bucket = LeakyBucket(rate=10.0, burst=5.0)
    acquired, wait_time = await bucket.acquire(tokens=1.0)
    assert acquired is True
    assert wait_time == 0.0


@pytest.mark.asyncio
async def test_leaky_bucket_acquire_returns_wait_time_when_depleted():
    # Burst of 1 token, rate of 1/s — one acquire drains it entirely.
    bucket = LeakyBucket(rate=1.0, burst=1.0)
    await bucket.acquire(tokens=1.0)
    acquired, wait_time = await bucket.acquire(tokens=1.0)
    assert acquired is False
    assert wait_time > 0.0


@pytest.mark.asyncio
async def test_enforce_rate_limit_sleeps_and_retries_when_rate_limited(monkeypatch):
    call_count = {"n": 0}

    async def fake_acquire(tokens=1.0):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return False, 0.1
        return True, 0.0

    monkeypatch.setattr(limitmod._bucket, "acquire", fake_acquire)

    slept = []

    async def fake_sleep(delay):
        slept.append(delay)

    monkeypatch.setattr(limitmod.asyncio, "sleep", fake_sleep)

    await enforce_rate_limit("test-id")

    assert call_count["n"] == 2
    assert slept == [pytest.approx(0.1)]
