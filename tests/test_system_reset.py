from types import SimpleNamespace
from unittest.mock import AsyncMock

from ibproxy.models import SystemStatus


def test_reset_endpoint_success(client, monkeypatch):
    """Test the /reset endpoint successfully reconnects and returns status."""
    # Use existing auth, just replace it with a mock
    from ibproxy import main
    from ibproxy.system import reset as reset_module

    mock_auth = AsyncMock()
    mock_auth.logout = AsyncMock()
    mock_auth.status = AsyncMock(return_value=SimpleNamespace(connected=False))
    mock_auth.connect = AsyncMock()
    main.app.state.auth = mock_auth

    # Mock get_system_status
    dummy_status = SystemStatus(label="Normal Operations", colour="🟩")

    async def mock_get_system_status():
        return dummy_status

    monkeypatch.setattr(reset_module, "get_system_status", mock_get_system_status)

    # Make the request
    response = client.post("/reset")

    assert response.status_code == 200
    assert response.json() == dummy_status.model_dump()

    # Verify auth.connect() was called
    mock_auth.connect.assert_called_once()


def test_reset_endpoint_auth_failure(client, monkeypatch, caplog):
    """Test the /reset endpoint when authentication fails."""
    # Use existing auth, just replace it with a mock
    from ibproxy import main
    from ibproxy.system import reset as reset_module

    mock_auth = AsyncMock()
    mock_auth.logout = AsyncMock()
    mock_auth.status = AsyncMock(return_value=SimpleNamespace(connected=False))
    mock_auth.connect = AsyncMock(side_effect=Exception("Auth failed"))
    main.app.state.auth = mock_auth

    # Mock get_system_status to succeed anyway (endpoint should still return status)
    dummy_status = SystemStatus(label="Problem / Outage", colour="🟥")

    async def mock_get_system_status():
        return dummy_status

    monkeypatch.setattr(reset_module, "get_system_status", mock_get_system_status)

    # Make the request
    response = client.post("/reset")

    assert response.status_code == 200
    assert response.json() == dummy_status.model_dump()

    # Verify error was logged
    assert "Authentication failed!" in caplog.text


def test_reset_endpoint_status_fetch_failure(client, monkeypatch):
    """Test the /reset endpoint when fetching system status fails."""
    # Use existing auth, just replace it with a mock
    from ibproxy import main
    from ibproxy.system import reset as reset_module

    mock_auth = AsyncMock()
    mock_auth.logout = AsyncMock()
    mock_auth.status = AsyncMock(return_value=SimpleNamespace(connected=False))
    mock_auth.connect = AsyncMock()
    main.app.state.auth = mock_auth

    # Mock get_system_status to raise RuntimeError
    async def mock_get_system_status():
        raise RuntimeError("Failed to parse IBKR status page!")

    monkeypatch.setattr(reset_module, "get_system_status", mock_get_system_status)

    # Make the request
    response = client.post("/reset")

    assert response.status_code == 502
    assert "Failed to parse IBKR status page!" in response.json()["detail"]


def test_reset_endpoint_uses_correct_config(client, monkeypatch):
    """Test that the /reset endpoint uses the config from app state."""
    from ibproxy import main
    from ibproxy.system import reset as reset_module

    # Set a specific config path in app state
    test_config_path = "test-config.yaml"
    main.app.state.args = SimpleNamespace(config=test_config_path)

    # Ensure we do not recreate auth; use existing object
    prev_auth = AsyncMock()
    prev_auth.logout = AsyncMock()
    prev_auth.status = AsyncMock(return_value=SimpleNamespace(connected=False))
    prev_auth.connect = AsyncMock()
    main.app.state.auth = prev_auth

    # Mock get_system_status
    dummy_status = SystemStatus(label="Normal Operations", colour="🟩")

    async def mock_get_system_status():
        return dummy_status

    monkeypatch.setattr(reset_module, "get_system_status", mock_get_system_status)

    # Make the request
    response = client.post("/reset")

    assert response.status_code == 200
    # Auth should not be recreated; still the same object
    assert main.app.state.auth is prev_auth
