from types import SimpleNamespace
from unittest.mock import AsyncMock

from ibproxy.models import SystemStatus


def test_reset_endpoint_success(client, monkeypatch):
    """Test the /reset endpoint successfully reconnects and returns status."""
    from ibproxy.system import reset as reset_module

    # Mock ibauth.auth_from_yaml
    mock_auth = AsyncMock()
    mock_auth.connect = AsyncMock()

    def mock_auth_from_yaml(config_path):
        return mock_auth

    monkeypatch.setattr("ibproxy.system.reset.ibauth.auth_from_yaml", mock_auth_from_yaml)

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
    from ibproxy.system import reset as reset_module

    # Mock ibauth.auth_from_yaml to raise an exception on connect
    mock_auth = AsyncMock()
    mock_auth.connect = AsyncMock(side_effect=Exception("Auth failed"))

    def mock_auth_from_yaml(config_path):
        return mock_auth

    monkeypatch.setattr("ibproxy.system.reset.ibauth.auth_from_yaml", mock_auth_from_yaml)

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
    from ibproxy.system import reset as reset_module

    # Mock ibauth.auth_from_yaml
    mock_auth = AsyncMock()
    mock_auth.connect = AsyncMock()

    def mock_auth_from_yaml(config_path):
        return mock_auth

    monkeypatch.setattr("ibproxy.system.reset.ibauth.auth_from_yaml", mock_auth_from_yaml)

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

    # Track which config was used
    used_config = None

    mock_auth = AsyncMock()
    mock_auth.connect = AsyncMock()

    def mock_auth_from_yaml(config_path):
        nonlocal used_config
        used_config = config_path
        return mock_auth

    monkeypatch.setattr("ibproxy.system.reset.ibauth.auth_from_yaml", mock_auth_from_yaml)

    # Mock get_system_status
    dummy_status = SystemStatus(label="Normal Operations", colour="🟩")

    async def mock_get_system_status():
        return dummy_status

    monkeypatch.setattr(reset_module, "get_system_status", mock_get_system_status)

    # Make the request
    response = client.post("/reset")

    assert response.status_code == 200
    assert used_config == test_config_path
