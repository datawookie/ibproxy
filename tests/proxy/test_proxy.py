import bz2
import json
from datetime import datetime, timezone
from typing import Any, Dict

import pytest

import ibproxy.main as appmod
import ibproxy.rate as ratemod
from ibproxy.timing import timing


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
    body=b'{"ok": true}',
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

    class MockResponse:
        def __init__(self):
            self.content = body
            self.status_code = status
            self.headers = headers
            # minimal shape to satisfy .json() and .raise_for_status()

        def json(self):
            return json.loads(self.content.decode("utf-8"))

        def raise_for_status(self):
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


def test_proxy_forwards_and_strips_headers(client, monkeypatch, tmp_path):
    # Make dumps go to a temp place and fix the "now" used in rate.record()
    fixed_dt = datetime(2025, 8, 22, 12, 34, 56, 789000, tzinfo=timezone.utc)
    monkeypatch.setattr(appmod, "JOURNAL_DIR", tmp_path)

    # Patch rate.record() to avoid time dependence and to return the fixed datetime
    def _record(_path: str) -> datetime:
        # also maintain minimal realistic rate state
        ratemod.times[_path].append(fixed_dt.timestamp())
        return fixed_dt

    monkeypatch.setattr(appmod.rate, "record", _record)

    captured = _make_mock_httpx(monkeypatch)

    # Send a request through the ASGI app
    resp = client.get("/v1/api/portfolio/DUH638336/summary", params={"x": "1"}, headers={"X-From": "test"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    assert "content-length" in resp.headers
    assert "content-encoding" not in resp.headers
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

    # Journal file written with fixed datetime path
    expected_file = tmp_path / "20250822" / "20250822-123456:789000.json.bz2"
    assert expected_file.exists()
    with bz2.open(expected_file, "rt", encoding="utf-8") as fh:
        dump = json.load(fh)
    assert dump["request"]["url"].endswith("/v1/api/portfolio/DUH638336/summary")
    assert dump["response"] == {"ok": True}
    assert isinstance(dump["duration"], float)


def test_proxy_handles_post_json_body(client, monkeypatch, tmp_path):
    monkeypatch.setattr(appmod, "JOURNAL_DIR", tmp_path)

    captured = _make_mock_httpx(monkeypatch)
    payload = {"orders": [{"conid": 123, "side": "BUY"}]}

    resp = client.post("/v1/api/iserver/somepost", json=payload)
    assert resp.status_code == 200
    # Upstream got the raw JSON bytes (content, not form-encoded)
    assert json.loads(captured["content"].decode("utf-8")) == payload


def test_rate_module_sliding_window(monkeypatch):
    # Control time to make the math deterministic
    t0 = 1_000_000.0
    times = [t0, t0 + 1, t0 + 2, t0 + 7]  # last one falls outside default WINDOW=5 for earlier entries

    i = {"i": 0}

    def fake_time():
        v = times[i["i"]]
        i["i"] += 1
        return v

    monkeypatch.setattr(ratemod, "WINDOW", 5)
    monkeypatch.setattr("time.time", fake_time)

    ep = "/x"
    ratemod.times.clear()
    ratemod.record(ep)  # t0
    ratemod.record(ep)  # t0+1
    ratemod.record(ep)  # t0+2
    # Now jump ahead by 5 seconds; previous earliest should be pruned
    ratemod.record(ep)  # t0+7

    rps, period = ratemod.rate(ep)
    # we only have the last two timestamps in the window: [t0+2, t0+7] -> n=2, elapsed=5 => rps=0.4
    assert rps is not None and abs(rps - 0.4) < 1e-6
    assert period is not None and abs(period - 2.5) < 1e-6


def test_timing_context_measures_time():
    with timing() as t:
        # do nothing substantial; duration should be a small positive float
        pass
    assert isinstance(t.duration, float)
    assert t.duration >= 0.0
