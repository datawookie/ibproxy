import bz2
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from freezegun import freeze_time

import ibproxy.const as constmod
import ibproxy.main as appmod
import ibproxy.rate as ratemod
from ibproxy.system.status import STATUS_COLOURS


class _MockAuth:
    domain = "localhost:5000"
    bearer_token = "BEARER-TOKEN"

    def tickle(self) -> None: ...
    def get_access_token(self) -> None: ...
    def get_bearer_token(self) -> None: ...
    def ssodh_init(self) -> None: ...
    def validate_sso(self) -> None: ...
    def logout(self) -> None: ...


@pytest.fixture(autouse=True)
def _clean_rate_and_auth(monkeypatch):
    # fresh rate state for each test
    ratemod.times.clear()
    # set a mock auth so routes can build the upstream URL/header
    monkeypatch.setattr(appmod, "auth", _MockAuth())
    yield
    ratemod.times.clear()


def _make_mock_httpx(
    monkeypatch,
    *,
    status=200,
    body: bytes | str = b'{"ok": true}',
    headers: Dict[str, str] | None = None,
    capture: Dict[str, Any] | None = None,
):
    """
    Patch httpx.AsyncClient.request to return a canned response and
    optionally capture the forwarded request data.
    """
    if headers is None:
        headers = {
            "content-type": "application/json",
            "content-length": "999",  # bogus on purpose
            "content-encoding": "gzip",  # bogus on purpose
        }
    if capture is None:
        capture = {}
    if not isinstance(body, bytes):
        body = body.encode("utf-8")

    class MockResponse:
        def __init__(self):
            self.content = body
            self.text = str(body, "utf-8")
            self.status_code = status
            self.request = Mock()
            self.request.headers = headers
            # Make response headers same as request headers.
            self.headers = headers

            self.is_error = not (200 <= self.status_code < 400)

        def json(self) -> dict[str, Any]:
            return json.loads(self.content.decode("utf-8"))

        def raise_for_status(self) -> None:
            if not (200 <= self.status_code < 400):
                raise Exception(f"status {self.status_code}")

    async def fake_request(self, *, method, url, content, headers, params, timeout):
        # stash what the proxy sent upstream
        capture["method"] = method
        capture["url"] = url
        capture["content"] = content
        capture["headers"] = headers
        capture["params"] = params
        capture["timeout"] = timeout
        return MockResponse()

    # Patch just the bound method on AsyncClient
    monkeypatch.setattr(
        "httpx.AsyncClient.request",
        fake_request,
        raising=True,
    )
    return capture


@pytest.mark.asyncio
@freeze_time("2025-08-22T12:34:56.789000Z")
async def test_proxy_forwards_and_strips_headers(client, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(appmod, "JOURNAL_DIR", tmp_path)

    # Patch rate.record() to avoid time dependence and to return the fixed datetime
    async def _record(_path: str) -> datetime:
        # Maintain minimal realistic rate state.
        now = datetime.now(tz=timezone.utc)
        ratemod.times[_path].append(now.timestamp())
        return now

    monkeypatch.setattr(ratemod, "record", _record)

    captured = _make_mock_httpx(monkeypatch)

    resp = client.get("/v1/api/portfolio/DUH638336/summary", params={"x": "1"}, headers={"X-From": "test"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    request_id = resp.headers.get("X-Request-ID")

    assert "content-encoding" in resp.headers
    assert "gzip" in resp.headers["content-encoding"]
    assert resp.headers["content-type"].startswith("application/json")

    # Upstream call received expected forwarding bits
    assert captured["method"] == "GET"
    assert captured["url"].endswith("/v1/api/portfolio/DUH638336/summary")
    # Host header must have been removed before forwarding
    fwd_headers = {k.lower(): v for k, v in captured["headers"].items()}
    assert "host" not in fwd_headers
    # Our Authorization header injected
    assert fwd_headers.get("authorization") == "Bearer BEARER-TOKEN"
    # Proxy preserved custom header
    assert fwd_headers.get("x-from") == "test"
    # Query params forwarded
    assert captured["params"] == {"x": "1"}

    expected_file = tmp_path / "20250822" / f"20250822-123456-{request_id}.json.bz2"
    assert expected_file.exists()
    with bz2.open(expected_file, "rt", encoding="utf-8") as fh:
        dump = json.load(fh)
    assert dump["request"]["url"].endswith("/v1/api/portfolio/DUH638336/summary")
    assert dump["request"]["params"] == {"x": "1"}
    assert dump["response"]["data"] == {"ok": True}
    assert isinstance(dump["duration"], float)


def test_proxy_handles_post_json_body(client, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(appmod, "JOURNAL_DIR", tmp_path)

    captured = _make_mock_httpx(monkeypatch)
    payload = {"orders": [{"conid": 123, "side": "BUY"}]}

    resp = client.post("/v1/api/iserver/somepost", json=payload)
    assert resp.status_code == 200
    # Upstream got the raw JSON bytes (content, not form-encoded)
    assert json.loads(captured["content"].decode("utf-8")) == payload


@pytest.mark.asyncio
async def test_rate_module_sliding_window(monkeypatch) -> None:
    # Control time to make the math deterministic
    t0 = 1_000_000.0
    times = [t0, t0 + 1, t0 + 2, t0 + 7]  # last one falls outside default WINDOW for earlier entries

    i = {"i": 0}

    def fake_time():
        v = times[i["i"]]
        i["i"] += 1
        return v

    monkeypatch.setattr(ratemod, "WINDOW", 5)
    monkeypatch.setattr("time.time", fake_time)

    path = "/test"
    ratemod.times.clear()
    await ratemod.record(path)  # t0
    await ratemod.record(path)  # t0+1
    await ratemod.record(path)  # t0+2
    # Now jump ahead by 5 seconds; previous earliest should be pruned
    await ratemod.record(path)  # t0+7

    rps, period = await ratemod.rate(path)
    # we only have the last two timestamps in the window: [t0+2, t0+7] -> n=2, elapsed=5 => rps=0.4
    assert rps is not None and abs(rps - 0.4) < 1e-6
    assert period is not None and abs(period - 2.5) < 1e-6


def test_proxy_handles_request_error(client, monkeypatch) -> None:
    # Patch AsyncClient.request to raise a RequestError
    async def raise_request_error(*args, **kwargs):
        raise httpx.RequestError("boom")

    monkeypatch.setattr("ibproxy.main.httpx.AsyncClient.request", raise_request_error)

    resp = client.get("/test")

    assert resp.status_code == 502
    assert resp.json() == {"error": "Proxy error: boom"}


@pytest.mark.asyncio
@patch("ibproxy.main.uvicorn.run")
@patch("ibproxy.main.ibauth.auth_from_yaml")
@patch("ibproxy.main.argparse.ArgumentParser.parse_args")
@patch("ibproxy.tickle.get_system_status", new_callable=AsyncMock)
async def test_main_runs_with_auth_and_uvicorn(
    mock_get_status, mock_parse_args, mock_auth_from_yaml, mock_uvicorn
) -> None:
    mock_get_status.return_value = STATUS_COLOURS["#66cc33"]

    # Pretend --debug not passed.
    mock_parse_args.return_value = Mock(debug=False, port=constmod.API_PORT, config="config.yaml")

    # Fake auth object with methods.
    auth = AsyncMock()
    mock_auth_from_yaml.return_value = auth

    appmod.main()

    # Trigger the lifespan events.
    async with appmod.lifespan(appmod.app):
        pass

    # Auth constructed from config.yaml.
    mock_auth_from_yaml.assert_called_once_with("config.yaml")

    # Uvicorn should be launched with expected args.
    mock_uvicorn.assert_called_once()
    args, kwargs = mock_uvicorn.call_args
    assert kwargs["host"] == constmod.API_HOST
    assert kwargs["port"] == constmod.API_PORT
    assert kwargs["workers"] == 1
    assert kwargs["reload"] is False

    # Logout should happen after uvicorn.run().
    auth.logout.assert_called_once()


@pytest.mark.asyncio
@freeze_time("2025-08-29T15:00:10.000000Z")
async def test_upstream_500_results_in_502_and_logs(
    monkeypatch, client, caplog: pytest.LogCaptureFixture, tmp_path
) -> None:
    # Capture all logging at DEBUG level and above.
    caplog.set_level(logging.DEBUG)

    monkeypatch.setattr(appmod, "JOURNAL_DIR", tmp_path)

    # TODO: This is repeated from another test. Factor into separate function or fixture.
    async def _record(_path: str) -> datetime:
        # Maintain minimal realistic rate state.
        now = datetime.now(tz=timezone.utc)
        ratemod.times[_path].append(now.timestamp())
        return now

    monkeypatch.setattr(ratemod, "record", _record)

    ERROR_BODY = '{"error": "Service Unavailable", "statusCode": 503}'

    _make_mock_httpx(monkeypatch, status=503, body=ERROR_BODY)

    resp = client.get("/v1/api/portfolio/DUH638336/summary")

    request_id = resp.headers.get("X-Request-ID")

    assert resp.status_code == 502
    body = resp.json()
    assert body.get("error") == "Upstream service error."
    assert body.get("upstream_status") == 503
    assert body.get("detail") == ERROR_BODY

    assert any("Upstream API error 503" in rec.message for rec in caplog.records)

    expected_file = tmp_path / "20250829" / f"20250829-150010-{request_id}.json.bz2"
    assert expected_file.exists()
    with bz2.open(expected_file, "rt", encoding="utf-8") as fh:
        dump = json.load(fh)
    assert dump["request"]["url"].endswith("/v1/api/portfolio/DUH638336/summary")
    assert json.dumps(dump["response"]["data"]) == ERROR_BODY
    assert isinstance(dump["duration"], float)
