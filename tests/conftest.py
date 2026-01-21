from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

import ibproxy.main as appmod

REQUEST_ID = "test-req-id"


@pytest.fixture
def client(monkeypatch) -> TestClient:
    # Avoid the real tickle loop doing anything noisy.
    async def _noop_loop():
        return

    monkeypatch.setattr(appmod, "tickle_loop", _noop_loop)

    # Ensure app state has args and started_at for tests that expect them.
    appmod.app.state.args = SimpleNamespace(config="config.yaml", tickle_mode="always", tickle_interval=0.01)
    appmod.app.state.started_at = datetime.now(UTC)

    return TestClient(appmod.app)


@pytest.fixture
def dummy_response() -> httpx.Response:
    return httpx.Response(
        200,
        request=httpx.Request("GET", "https://api.test/test"),
        json={"ok": True},
    )


@pytest.fixture(autouse=True)
def fake_auth(monkeypatch):
    fake = SimpleNamespace(domain="api.test", bearer_token="token123", authenticated=True)
    appmod.app.state.auth = fake
    return fake


class DummyAuth:
    def __init__(self, authenticated=True):
        self.bearer_token = "abc123"
        self.authenticated = authenticated
        self.calls = 0

    async def connect(self):
        pass

    async def logout(self):
        pass

    def tickle(self):
        self.calls += 1


class DummyAuthFlaky(DummyAuth):
    def __init__(self):
        super().__init__()
        self.raised = False

    def tickle(self):
        self.calls += 1
        if not self.raised:
            self.raised = True
            raise RuntimeError("boom")
