from unittest.mock import MagicMock

import stress


def test_stress_request_makes_get_and_raises_for_status(monkeypatch):
    mock_response = MagicMock()
    mock_get = MagicMock(return_value=mock_response)
    monkeypatch.setattr(stress.httpx, "get", mock_get)

    result = stress.request("/test/endpoint")

    mock_get.assert_called_once_with("http://127.0.0.1:9000/v1/api/test/endpoint")
    mock_response.raise_for_status.assert_called_once()
    assert result is mock_response


def test_stress_main_hits_all_endpoints(monkeypatch):
    calls = []

    def mock_request(path):
        calls.append(path)
        return MagicMock()

    monkeypatch.setattr(stress, "request", mock_request)
    monkeypatch.setattr(stress.time, "sleep", MagicMock())

    stress.main()

    assert "/iserver/accounts" in calls
    assert "/portfolio/subaccounts" in calls
    assert "/fyi/notifications" in calls
    assert "/fyi/settings" in calls
    assert calls.count("/trsrv/stocks?symbols=AAPL") == 3
    assert calls.count("/trsrv/futures?symbols=ES") == 3
