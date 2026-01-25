import re
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import ibproxy.main as ibproxy


@pytest.mark.asyncio
@patch("ibproxy.main.httpx.AsyncClient.request")
async def test_proxy_logs_headers_and_params(
    mock_http_request, caplog: pytest.LogCaptureFixture, dummy_response, mock_request
):
    """Proxy should log headers and query params when debug logging is enabled."""
    mock_http_request.return_value = dummy_response

    # Create request with query params and headers using the factory
    request = mock_request.update(
        method="POST",
        query_string=b"foo=bar",
        headers=[(b"content-type", b"application/json"), (b"host", b"example.com")],
    )
    request._body = b'{"x":1}'

    caplog.set_level("DEBUG")

    await ibproxy.proxy("test", request)

    logs = [rec.getMessage() for rec in caplog.records]
    assert any("- Headers:" in m for m in logs)
    assert any("content-type" in m for m in logs)
    assert any("- Params:" in m for m in logs)
    assert any("foo" in m and "bar" in m for m in logs)


def test_proxy_logs_request(caplog: pytest.LogCaptureFixture, dummy_response, client: TestClient):
    with patch("ibproxy.main.httpx.AsyncClient.request", return_value=dummy_response):
        caplog.set_level("INFO")
        resp = client.get("/test")
        assert resp.status_code == 200

        logs = [rec.getMessage() for rec in caplog.records]
        assert any(re.match(r"🔵 Request: \[.*\] GET", m) for m in logs)
        assert any("✅ Return response." in m for m in logs)
