import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest
from fastapi import Request
from fastapi.testclient import TestClient

import ibproxy.main as appmod

REQUEST_ID = "test-req-id"


@pytest.fixture(autouse=True)
def disable_rate_limit(monkeypatch):
    """
    Disable rate limiting for tests.

    This is particularly important for tests that freeze time.
    """

    async def _noop_enforce(_id: str) -> None:
        return

    monkeypatch.setattr(appmod, "enforce_rate_limit", _noop_enforce)


@pytest.fixture(autouse=True)
def journal_dir_temporary(monkeypatch, tmp_path):
    """
    Set journal directory to a temporary location for tests.
    """
    monkeypatch.setattr(appmod, "JOURNAL_DIR", tmp_path)


@pytest.fixture
def client(monkeypatch) -> TestClient:
    # Avoid the real tickle loop doing anything noisy.
    async def _noop_loop():
        return

    monkeypatch.setattr(appmod, "tickle_loop", _noop_loop)

    # Ensure app state has args and started_at for tests that expect them.
    appmod.app.state.args = SimpleNamespace(config="config.yaml", tickle_mode="always", tickle_interval=0.01)
    appmod.app.state.started_at = datetime.now(UTC)

    # Ensure gate exists for tests that call the app directly.
    gate = asyncio.Event()
    gate.set()
    appmod.app.state.gate = gate

    # Provide an AsyncClient so the proxy handler can forward requests.
    http_client = httpx.AsyncClient()
    appmod.app.state.client = http_client

    client = TestClient(appmod.app)
    try:
        yield client
    finally:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(http_client.aclose())
        finally:
            loop.close()


@pytest.fixture
def dummy_response() -> httpx.Response:
    return httpx.Response(
        200,
        request=httpx.Request("GET", "https://api.test/test"),
        json={"ok": True},
    )


@pytest.fixture(autouse=True)
def fake_auth(monkeypatch):
    auth = DummyAuth(authenticated=True)
    auth.domain = "api.test"
    appmod.app.state.auth = auth
    return auth


@pytest.fixture
def mock_request() -> Request:
    """
    Create a mock Request for tests.

    Usage:
        # Default request
        request = mock_request

        # Or create custom request by passing parameters to factory
        request = mock_request(query_string=b"foo=bar", headers=[(b"content-type", b"application/json")])
    """

    def _update(
        method: str = "GET",
        path: str = "/test",
        query_string: bytes = b"",
        headers: list = None,
    ) -> Request:
        if headers is None:
            headers = []

        scope = {
            "type": "http",
            "method": method,
            "path": path,
            "headers": headers,
            "query_string": query_string,
            "app": appmod.app,
        }
        request = Request(scope)
        request.state.request_id = REQUEST_ID

        # Initialize the gate Event (normally done in lifespan).
        gate = asyncio.Event()
        gate.set()
        request.app.state.gate = gate

        request.app.state.client = httpx.AsyncClient()

        return request

    # Return the factory function, but also make it callable as the default request
    request = _update()
    request.update = _update
    return request


class DummyAuth:
    def __init__(self, authenticated=True):
        self.bearer_token = "abc123"
        self.authenticated = authenticated
        self.calls = 0

    async def connect(self):
        pass

    async def logout(self):
        pass

    async def status(self):
        return SimpleNamespace(connected=False)

    def is_connected(self):
        return self.authenticated

    async def tickle(self):
        self.calls += 1


class DummyAuthFlaky(DummyAuth):
    def __init__(self):
        super().__init__()
        self.raised = False

    async def tickle(self):
        self.calls += 1
        if not self.raised:
            self.raised = True
            raise RuntimeError("boom")
