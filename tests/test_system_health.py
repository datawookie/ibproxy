import ibproxy.main as appmod

from .conftest import DummyAuth


def test_health_degraded(monkeypatch, client):
    # Ensure auth is None
    monkeypatch.setattr(appmod.app.state, "auth", None)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "degraded"}


def test_health_ok(monkeypatch, client):
    monkeypatch.setattr(appmod.app.state, "auth", DummyAuth())
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_health_not_authenticated(monkeypatch, client):
    monkeypatch.setattr(appmod.app.state, "auth", DummyAuth(authenticated=False))
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "not authenticated"}
