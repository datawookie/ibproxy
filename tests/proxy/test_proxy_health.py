import proxy.main as appmod


def test_health_degraded(monkeypatch, client):
    # Ensure auth is None
    monkeypatch.setattr(appmod, "auth", None)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "degraded"}


def test_health_ok(monkeypatch, client):
    # Fake auth with a bearer_token
    class DummyAuth:
        bearer_token = "abc123"

    monkeypatch.setattr(appmod, "auth", DummyAuth())
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
