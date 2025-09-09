import ibproxy.main as appmod


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
        authenticated = True

    monkeypatch.setattr(appmod, "auth", DummyAuth())
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_health_not_authenticated(monkeypatch, client):
    # Fake auth with a bearer_token
    class DummyAuth:
        bearer_token = "abc123"
        authenticated = False

    monkeypatch.setattr(appmod, "auth", DummyAuth())
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "not authenticated"}
