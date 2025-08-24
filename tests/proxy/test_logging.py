from unittest.mock import patch

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

import ibproxy.main as ibproxy


@pytest.mark.asyncio
@patch("ibproxy.main.httpx.AsyncClient.request")
async def test_proxy_logs_headers_and_params(mock_request, caplog, dummy_response):
    """Proxy should log headers and query params when debug logging is enabled."""
    mock_request.return_value = dummy_response

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/test",
        "headers": [(b"content-type", b"application/json"), (b"host", b"example.com")],
        "query_string": b"foo=bar",
    }
    request = Request(scope)
    request._body = b'{"x":1}'  # fastapi Request caches body, hack it in

    caplog.set_level("DEBUG")

    await ibproxy.proxy("test", request)

    logs = [rec.getMessage() for rec in caplog.records]
    assert any("- Headers:" in m for m in logs)
    assert any("content-type" in m for m in logs)
    assert any("- Params:" in m for m in logs)
    assert any("foo" in m and "bar" in m for m in logs)


client = TestClient(ibproxy.app)


def test_proxy_logs_request(caplog, dummy_response):
    with patch("ibproxy.main.httpx.AsyncClient.request", return_value=dummy_response):
        caplog.set_level("INFO")
        resp = client.get("/test")
        assert resp.status_code == 200

        logs = [rec.getMessage() for rec in caplog.records]
        assert any("🔵 Request: GET" in m for m in logs)
        assert any("✅ Return response." in m for m in logs)
