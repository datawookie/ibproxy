import asyncio
import logging
import time
from typing import Iterator
from unittest.mock import Mock

import pytest

import ibproxy.main as appmod
import ibproxy.tickle as ticklemod


class DummyAuthOK:
    def __init__(self):
        self.calls = 0

    def tickle(self):
        self.calls += 1


class DummyAuthFlaky:
    def __init__(self):
        self.calls = 0
        self.raised = False

    def tickle(self):
        self.calls += 1
        if not self.raised:
            self.raised = True
            raise RuntimeError("boom")


async def empty_status():
    return Mock(colour="<>", label="<label>")


@pytest.fixture(autouse=True)
def noop_get_system_status(monkeypatch) -> Iterator[None]:
    monkeypatch.setattr(ticklemod, "get_system_status", empty_status)
    yield


@pytest.mark.asyncio
async def test_tickle_loop_calls_auth(monkeypatch):
    # make ticks frequent for the test
    monkeypatch.setattr(ticklemod, "TICKLE_INTERVAL", 0.01)
    # ensure we don't busy-loop when remaining time is tiny
    monkeypatch.setattr(ticklemod, "TICKLE_MIN_SLEEP", 0.001)

    # ensure rate.latest() returns None so tickle() is always called
    monkeypatch.setattr(appmod.rate, "latest", lambda: None)

    auth = DummyAuthOK()

    task = asyncio.create_task(appmod.tickle_loop(auth))
    # give it a little time to run several iterations
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # should have tickled multiple times
    assert auth.calls >= 2


@pytest.mark.asyncio
async def test_tickle_loop_logs_error(monkeypatch, caplog):
    monkeypatch.setattr(ticklemod, "TICKLE_INTERVAL", 0.01)
    monkeypatch.setattr(ticklemod, "TICKLE_MIN_SLEEP", 0.001)

    auth = DummyAuthFlaky()

    caplog.set_level(logging.DEBUG)
    task = asyncio.create_task(appmod.tickle_loop(auth))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # Error should have been logged during the first (failing) tickle.
    assert any("Tickle failed." in rec.message for rec in caplog.records)
    # tickle was attempted multiple times (first raised, subsequent success)
    assert auth.calls >= 2


@pytest.mark.asyncio
async def test_lifespan_starts_and_cancels(monkeypatch):
    monkeypatch.setattr(ticklemod, "TICKLE_INTERVAL", 0.01)
    monkeypatch.setattr(ticklemod, "TICKLE_MIN_SLEEP", 0.001)

    # make latest None so the tickle loop will call auth.tickle()
    monkeypatch.setattr(appmod.rate, "latest", lambda: None)

    auth = DummyAuthOK()
    monkeypatch.setattr(appmod, "auth", auth)

    # entering the lifespan should create the task
    async with appmod.lifespan(appmod.app):
        assert isinstance(appmod.tickle, asyncio.Task)
        # allow the loop to run a few times
        await asyncio.sleep(0.03)
        assert auth.calls >= 1

    # after exiting lifespan the task should be cancelled or finished
    assert appmod.tickle.cancelled() or appmod.tickle.done()


@pytest.mark.asyncio
async def test_tickle_auto_skips_when_latest_recent(monkeypatch, caplog):
    """
    If rate.latest() returns a timestamp within TICKLE_INTERVAL seconds ago,
    the loop should log "Within tickle interval..." and NOT call auth.tickle().
    """
    monkeypatch.setattr(ticklemod, "TICKLE_INTERVAL", 0.2)
    monkeypatch.setattr(ticklemod, "TICKLE_MIN_SLEEP", 0.01)

    latest = time.time() - (0.05 * ticklemod.TICKLE_INTERVAL)
    monkeypatch.setattr(appmod.rate, "latest", lambda: latest)

    auth = DummyAuthOK()

    task = asyncio.create_task(appmod.tickle_loop(auth, "auto"))
    # Wait long enough for the loop to call tickle once.
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # Because the last request was recent, tickle should NOT have been called.
    assert auth.calls == 0


@pytest.mark.asyncio
async def test_tickle_auto_calls_when_latest_old(monkeypatch, caplog):
    """
    If rate.latest() returns a timestamp older than TICKLE_INTERVAL, auth.tickle()
    should be invoked.
    """
    monkeypatch.setattr(ticklemod, "TICKLE_INTERVAL", 0.05)
    monkeypatch.setattr(ticklemod, "TICKLE_MIN_SLEEP", 0.001)

    latest = time.time() - (ticklemod.TICKLE_INTERVAL + 0.02)
    monkeypatch.setattr(appmod.rate, "latest", lambda: latest)

    auth = DummyAuthOK()

    task = asyncio.create_task(appmod.tickle_loop(auth, "auto"))
    # Wait long enough for the loop to call tickle once.
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # Tickle should have been called at least once.
    assert auth.calls >= 1


@pytest.mark.asyncio
async def test_tickle_off(monkeypatch, caplog):
    monkeypatch.setattr(ticklemod, "TICKLE_INTERVAL", 0.05)
    monkeypatch.setattr(ticklemod, "TICKLE_MIN_SLEEP", 0.001)

    auth = DummyAuthOK()

    caplog.set_level(logging.INFO)

    task = asyncio.create_task(appmod.tickle_loop(auth, "off"))
    # Wait long enough for the loop to call tickle once.
    await asyncio.sleep(0.2)
    task.cancel()
    await task

    assert any("Tickle loop disabled" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_tickle_always(monkeypatch, caplog):
    monkeypatch.setattr(ticklemod, "TICKLE_INTERVAL", 0.05)
    monkeypatch.setattr(ticklemod, "TICKLE_MIN_SLEEP", 0.001)

    auth = DummyAuthOK()

    task = asyncio.create_task(appmod.tickle_loop(auth, "always"))
    # Wait long enough for the loop to call tickle once.
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # Tickle should have been called at least once.
    assert auth.calls >= 1
