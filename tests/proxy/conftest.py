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
    fake = SimpleNamespace(domain="api.test", bearer_token="token123")
    monkeypatch.setattr("ibproxy.main.auth", fake)
    return fake
