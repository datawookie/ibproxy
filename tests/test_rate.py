from collections import deque

import pytest

import ibproxy.rate as ratemod


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
