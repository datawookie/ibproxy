from datetime import UTC, datetime, timedelta


def test_uptime_endpoint(client, monkeypatch):
    """Test the /uptime endpoint returns correct uptime information."""
    from ibproxy import main

    # Mock a started_at time that's 1 hour ago
    fake_start = datetime.now(UTC) - timedelta(hours=1)
    monkeypatch.setattr(main.app.state, "started_at", fake_start)

    response = client.get("/uptime")

    assert response.status_code == 200
    data = response.json()

    # Check response structure
    assert "started" in data
    assert "uptime_seconds" in data
    assert "uptime_human" in data

    # Verify started time matches our fake start
    started_dt = datetime.fromisoformat(data["started"].replace("Z", "+00:00"))
    assert abs((started_dt - fake_start).total_seconds()) < 1

    # Verify uptime is approximately 1 hour (3600 seconds)
    # Allow some tolerance for test execution time
    assert 3599 < data["uptime_seconds"] < 3605

    # Verify uptime_human is a string with time information
    assert isinstance(data["uptime_human"], str)
    assert ":" in data["uptime_human"]


def test_uptime_endpoint_just_started(client, monkeypatch):
    """Test the /uptime endpoint when the server just started."""
    from ibproxy import main

    # Mock a started_at time that's just now
    fake_start = datetime.now(UTC)
    monkeypatch.setattr(main.app.state, "started_at", fake_start)

    response = client.get("/uptime")

    assert response.status_code == 200
    data = response.json()

    # Uptime should be very close to 0
    assert data["uptime_seconds"] < 1
    assert isinstance(data["uptime_human"], str)


def test_uptime_endpoint_long_running(client, monkeypatch):
    """Test the /uptime endpoint for a long-running server."""
    from ibproxy import main

    # Mock a started_at time that's 7 days ago
    fake_start = datetime.now(UTC) - timedelta(days=7, hours=3, minutes=45)
    monkeypatch.setattr(main.app.state, "started_at", fake_start)

    response = client.get("/uptime")

    assert response.status_code == 200
    data = response.json()

    # Verify uptime is approximately 7 days + 3 hours + 45 minutes
    expected_seconds = 7 * 24 * 3600 + 3 * 3600 + 45 * 60
    # Allow some tolerance for test execution time
    assert expected_seconds - 5 < data["uptime_seconds"] < expected_seconds + 5

    # Verify uptime_human contains "day" or "days"
    assert "day" in data["uptime_human"].lower()
