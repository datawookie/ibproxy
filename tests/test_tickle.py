import asyncio
import logging
import time
from typing import Any, Iterator
from unittest.mock import AsyncMock, Mock, patch

import pytest

import ibproxy.const as constmod
import ibproxy.main as appmod
import ibproxy.tickle as ticklemod

from .conftest import DummyAuth, DummyAuthFlaky


async def empty_status():
    return Mock(colour="<>", label="<label>")


@pytest.fixture(autouse=True)
def noop_get_system_status(monkeypatch: Any, request: pytest.FixtureRequest) -> Iterator[None]:
    """
    Use @pytest.mark.disable_noop_get_system_status if you want the original _connect().
    """
    if request.node.get_closest_marker("disable_noop_get_system_status"):
        yield
        return

    monkeypatch.setattr(ticklemod, "get_system_status", empty_status)
    yield


@pytest.fixture
def timeout_get_system_status(monkeypatch: Any) -> Iterator[None]:
    mock = AsyncMock(side_effect=asyncio.TimeoutError("TimeoutError: Because even Python has limits on patience."))
    monkeypatch.setattr(ticklemod, "get_system_status", mock)
    yield


@pytest.mark.asyncio
async def test_tickle_loop_calls_auth(monkeypatch):
    # make ticks frequent for the test
    monkeypatch.setattr(ticklemod, "TICKLE_INTERVAL", 0.01)
    # ensure we don't busy-loop when remaining time is tiny
    monkeypatch.setattr(ticklemod, "TICKLE_MIN_SLEEP", 0.001)

    # ensure rate.latest() returns None so tickle() is always called
    monkeypatch.setattr(appmod.rate, "latest", lambda: None)

    auth = DummyAuth()

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
@patch("ibproxy.main.ibauth.auth_from_yaml")
@patch("ibproxy.main.argparse.ArgumentParser.parse_args")
async def test_lifespan_starts_and_cancels(mock_parse_args, mock_auth_from_yaml, monkeypatch):
    monkeypatch.setattr(ticklemod, "TICKLE_INTERVAL", 0.01)
    monkeypatch.setattr(ticklemod, "TICKLE_MIN_SLEEP", 0.001)

    # Pretend --debug not passed.
    mock_parse_args.return_value = Mock(debug=False, port=constmod.API_PORT, config="config.yaml")
    appmod.app.state.args = mock_parse_args.return_value

    # Make latest None so the tickle loop will call auth.tickle()
    monkeypatch.setattr(appmod.rate, "latest", lambda: None)

    auth = DummyAuth()
    mock_auth_from_yaml.return_value = auth

    # Trigger the lifespan events.
    async with appmod.lifespan(appmod.app):
        assert isinstance(appmod.tickle, asyncio.Task)
        # Allow the loop to run a few times.
        await asyncio.sleep(0.05)
        assert auth.calls >= 1

    assert appmod.tickle.cancelled() or appmod.tickle.done()


@pytest.mark.asyncio
@patch("ibproxy.main.ibauth.auth_from_yaml")
@patch("ibproxy.main.argparse.ArgumentParser.parse_args")
async def test_lifespan_tickle_exception(
    mock_parse_args, mock_auth_from_yaml, monkeypatch, caplog: pytest.LogCaptureFixture
):
    """
    This is testing important functionality. If the tickle loop dies then we
    want to know about it.
    """
    caplog.set_level(logging.INFO)

    # Pretend --debug not passed.
    mock_parse_args.return_value = Mock(debug=False, port=constmod.API_PORT, config="config.yaml")
    appmod.app.state.args = mock_parse_args.return_value

    auth = DummyAuth()
    mock_auth_from_yaml.return_value = auth

    async def explode(*args, **kwargs):
        raise RuntimeError("Boom")

    monkeypatch.setattr(appmod, "tickle_loop", explode)

    monkeypatch.setattr(appmod.rate, "latest", lambda: None)

    async with appmod.lifespan(appmod.app):
        assert isinstance(appmod.tickle, asyncio.Task)
        await asyncio.sleep(0.03)

    print([rec.message for rec in caplog.records])

    assert any("Tickle task terminated with exception: Boom" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_tickle_auto_skips_when_latest_recent(monkeypatch, caplog: pytest.LogCaptureFixture):
    """
    If rate.latest() returns a timestamp within TICKLE_INTERVAL seconds ago,
    the loop should log "Within tickle interval..." and NOT call auth.tickle().
    """
    monkeypatch.setattr(ticklemod, "TICKLE_INTERVAL", 0.2)
    monkeypatch.setattr(ticklemod, "TICKLE_MIN_SLEEP", 0.01)

    latest = time.time() - (0.05 * ticklemod.TICKLE_INTERVAL)
    monkeypatch.setattr(appmod.rate, "latest", lambda: latest)

    auth = DummyAuth()

    task = asyncio.create_task(appmod.tickle_loop(auth, "auto"))
    # Wait long enough for the loop to call tickle once.
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # Because the last request was recent, tickle should NOT have been called.
    assert auth.calls == 0


@pytest.mark.asyncio
async def test_tickle_auto_calls_when_latest_old(monkeypatch, caplog: pytest.LogCaptureFixture):
    """
    If rate.latest() returns a timestamp older than TICKLE_INTERVAL, auth.tickle()
    should be invoked.
    """
    monkeypatch.setattr(ticklemod, "TICKLE_INTERVAL", 0.05)
    monkeypatch.setattr(ticklemod, "TICKLE_MIN_SLEEP", 0.001)

    latest = time.time() - (ticklemod.TICKLE_INTERVAL + 0.02)
    monkeypatch.setattr(appmod.rate, "latest", lambda: latest)

    auth = DummyAuth()

    task = asyncio.create_task(appmod.tickle_loop(auth, "auto"))
    # Wait long enough for the loop to call tickle once.
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # Tickle should have been called at least once.
    assert auth.calls >= 1


@pytest.mark.asyncio
async def test_tickle_off(monkeypatch, caplog: pytest.LogCaptureFixture):
    monkeypatch.setattr(ticklemod, "TICKLE_INTERVAL", 0.05)
    monkeypatch.setattr(ticklemod, "TICKLE_MIN_SLEEP", 0.001)

    auth = DummyAuth()

    caplog.set_level(logging.INFO)

    task = asyncio.create_task(appmod.tickle_loop(auth, "off"))
    # Wait long enough for the loop to call tickle once.
    await asyncio.sleep(0.2)
    task.cancel()
    await task

    assert any("Tickle loop disabled" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_tickle_always(monkeypatch, caplog: pytest.LogCaptureFixture):
    monkeypatch.setattr(ticklemod, "TICKLE_INTERVAL", 0.05)
    monkeypatch.setattr(ticklemod, "TICKLE_MIN_SLEEP", 0.001)

    auth = DummyAuth()

    task = asyncio.create_task(appmod.tickle_loop(auth, "always"))
    # Wait long enough for the loop to call tickle once.
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # Tickle should have been called at least once.
    assert auth.calls >= 1


@pytest.mark.asyncio
@pytest.mark.disable_noop_get_system_status
async def test_tickle_status_timeout(timeout_get_system_status, monkeypatch, caplog: pytest.LogCaptureFixture):
    monkeypatch.setattr(ticklemod, "TICKLE_INTERVAL", 0.05)
    monkeypatch.setattr(ticklemod, "TICKLE_MIN_SLEEP", 0.001)

    auth = DummyAuth()

    task = asyncio.create_task(appmod.tickle_loop(auth, "always"))
    # Wait long enough for the loop to call tickle once.
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert any("IBKR status timed out!" in rec.message for rec in caplog.records)

    # Tickle should have been called at least once.
    assert auth.calls >= 1
