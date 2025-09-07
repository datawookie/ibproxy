import asyncio
import logging
import time
from typing import Iterator
from unittest.mock import Mock

import pytest

import ibproxy.main as appmod


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
    return Mock(colour="", label="")


@pytest.fixture(autouse=True)
def noop_get_system_status(monkeypatch) -> Iterator[None]:
    monkeypatch.setattr(appmod, "get_system_status", empty_status)
    yield


@pytest.mark.asyncio
async def test_tickle_loop_calls_auth(monkeypatch):
    # make ticks frequent for the test
    monkeypatch.setattr(appmod, "TICKLE_INTERVAL", 0.01)
    # ensure we don't busy-loop when remaining time is tiny
    monkeypatch.setattr(appmod, "TICKLE_MIN_SLEEP", 0.001)

    # ensure rate.latest() returns None so tickle() is always called
    monkeypatch.setattr(appmod.rate, "latest", lambda: None)

    dummy = DummyAuthOK()
    monkeypatch.setattr(appmod, "auth", dummy)

    task = asyncio.create_task(appmod.tickle_loop())
    # give it a little time to run several iterations
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # should have tickled multiple times
    assert dummy.calls >= 2


@pytest.mark.asyncio
async def test_tickle_loop_logs_error(monkeypatch, caplog):
    monkeypatch.setattr(appmod, "TICKLE_INTERVAL", 0.01)
    monkeypatch.setattr(appmod, "TICKLE_MIN_SLEEP", 0.001)

    # force latest to None so tickle() is invoked
    monkeypatch.setattr(appmod.rate, "latest", lambda: None)

    dummy = DummyAuthFlaky()
    monkeypatch.setattr(appmod, "auth", dummy)

    caplog.set_level(logging.ERROR)
    task = asyncio.create_task(appmod.tickle_loop())
    await asyncio.sleep(0.04)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # an error should have been logged during the first failing tickle
    assert any("Tickle failed:" in rec.message for rec in caplog.records)
    # tickle was attempted multiple times (first raised, subsequent success)
    assert dummy.calls >= 2


@pytest.mark.asyncio
async def test_lifespan_starts_and_cancels(monkeypatch):
    monkeypatch.setattr(appmod, "TICKLE_INTERVAL", 0.01)
    monkeypatch.setattr(appmod, "TICKLE_MIN_SLEEP", 0.001)

    # make latest None so the tickle loop will call auth.tickle()
    monkeypatch.setattr(appmod.rate, "latest", lambda: None)

    dummy = DummyAuthOK()
    monkeypatch.setattr(appmod, "auth", dummy)

    # entering the lifespan should create the task
    async with appmod.lifespan(appmod.app):
        assert isinstance(appmod.tickle, asyncio.Task)
        # allow the loop to run a few times
        await asyncio.sleep(0.03)
        assert dummy.calls >= 1

    # after exiting lifespan the task should be cancelled or finished
    assert appmod.tickle.cancelled() or appmod.tickle.done()


@pytest.mark.asyncio
async def test_tickle_skips_when_latest_recent(monkeypatch, caplog):
    """
    If rate.latest() returns a timestamp within TICKLE_INTERVAL seconds ago,
    the loop should log "Within tickle interval..." and NOT call auth.tickle().
    """
    # Make the interval small for test speed
    monkeypatch.setattr(appmod, "TICKLE_INTERVAL", 0.2)
    monkeypatch.setattr(appmod, "TICKLE_MIN_SLEEP", 0.01)

    # fixed "latest" timestamp: half the interval ago -> should be considered recent
    latest = time.time() - (0.5 * appmod.TICKLE_INTERVAL)
    monkeypatch.setattr(appmod.rate, "latest", lambda: latest)

    dummy = DummyAuthOK()
    monkeypatch.setattr(appmod, "auth", dummy)

    caplog.set_level(logging.INFO)

    task = asyncio.create_task(appmod.tickle_loop())
    # give the loop a small amount of time to execute the branch and log (but not to wait a full interval)
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # It should have logged the latest request line and the "Within tickle interval" message
    msgs = [rec.message for rec in caplog.records]
    assert any("Latest request:" in m for m in msgs), f"logs: {msgs}"
    assert any("Within tickle interval" in m for m in msgs), f"logs: {msgs}"

    # Because the last request was recent, tickle should NOT have been called
    assert dummy.calls == 0


@pytest.mark.asyncio
async def test_tickle_calls_when_latest_old(monkeypatch, caplog):
    """
    If rate.latest() returns a timestamp older than TICKLE_INTERVAL, auth.tickle()
    should be invoked.
    """
    monkeypatch.setattr(appmod, "TICKLE_INTERVAL", 0.05)
    monkeypatch.setattr(appmod, "TICKLE_MIN_SLEEP", 0.001)

    # fixed "latest" timestamp: older than the interval => should trigger tickle
    latest = time.time() - (appmod.TICKLE_INTERVAL + 0.02)
    monkeypatch.setattr(appmod.rate, "latest", lambda: latest)

    dummy = DummyAuthOK()
    monkeypatch.setattr(appmod, "auth", dummy)

    caplog.set_level(logging.INFO)

    task = asyncio.create_task(appmod.tickle_loop())
    # wait long enough for the loop to call tickle once
    await asyncio.sleep(0.06)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    msgs = [rec.message for rec in caplog.records]
    assert any("Latest request:" in m for m in msgs), f"logs: {msgs}"
    # Should NOT contain "Within tickle interval" because we're testing the old case
    assert not any("Within tickle interval" in m for m in msgs), f"logs: {msgs}"

    # tickle should have been called at least once
    assert dummy.calls >= 1
