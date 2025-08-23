import asyncio
import logging

import pytest

import proxy.main as appmod


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


@pytest.mark.asyncio
async def test_tickle_loop_calls_auth(monkeypatch):
    monkeypatch.setattr(appmod, "TICKLE_INTERVAL", 0.01)
    dummy = DummyAuthOK()
    monkeypatch.setattr(appmod, "auth", dummy)

    task = asyncio.create_task(appmod.tickle_loop())
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert dummy.calls >= 2


@pytest.mark.asyncio
async def test_tickle_loop_logs_error(monkeypatch, caplog):
    monkeypatch.setattr(appmod, "TICKLE_INTERVAL", 0.01)
    dummy = DummyAuthFlaky()
    monkeypatch.setattr(appmod, "auth", dummy)

    caplog.set_level(logging.ERROR)
    task = asyncio.create_task(appmod.tickle_loop())
    await asyncio.sleep(0.04)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert any("Tickle failed:" in rec.message for rec in caplog.records)
    assert dummy.calls >= 2


@pytest.mark.asyncio
async def test_lifespan_starts_and_cancels(monkeypatch):
    monkeypatch.setattr(appmod, "TICKLE_INTERVAL", 0.01)
    dummy = DummyAuthOK()
    monkeypatch.setattr(appmod, "auth", dummy)

    async with appmod.lifespan(appmod.app):
        assert isinstance(appmod.tickle, asyncio.Task)
        await asyncio.sleep(0.03)
        assert dummy.calls >= 1

    assert appmod.tickle.cancelled() or appmod.tickle.done()
