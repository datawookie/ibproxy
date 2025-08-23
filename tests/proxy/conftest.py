import pytest
from fastapi.testclient import TestClient

import proxy.main as appmod


@pytest.fixture
def client(monkeypatch) -> TestClient:
    # Avoid the real tickle loop doing anything noisy.
    async def _noop_loop():
        return

    monkeypatch.setattr(appmod, "tickle_loop", _noop_loop)
    return TestClient(appmod.app)
