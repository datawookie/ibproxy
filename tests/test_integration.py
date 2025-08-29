import os
import time
from typing import Any, Dict

import httpx
import pytest

PROXY_URL = os.getenv("PROXY_URL", "http://127.0.0.1:9000")
ACCOUNT_ID = os.getenv("IBKR_ACCOUNT_ID", "DUH638336")

DEFAULT_HEADERS = {
    "Accept": "*/*",
    "Connection": "keep-alive",
    "User-Agent": "ibproxy-integration-test",
    "Accept-Encoding": "gzip,deflate",
}

REQUEST_TIMEOUT = 5.0


def _get_response(client: httpx.Client, url: str) -> Dict[str, Any]:
    return client.get(url, headers=DEFAULT_HEADERS)


@pytest.fixture(scope="session")
def client() -> httpx.Client:
    return httpx.Client(base_url=PROXY_URL, timeout=REQUEST_TIMEOUT, verify=False)


@pytest.fixture(scope="session", autouse=True)
def _ensure_proxy_running(client: httpx.Client):
    """Skip the integration suite if the proxy is not reachable."""
    try:
        health = client.get("/health")
        if health.status_code in (200, 404):
            return
    except Exception:
        pass
    pytest.skip(f"Proxy not reachable at {PROXY_URL}; set PROXY_URL or start the service.")


@pytest.mark.integration
def test_portfolio_summary(client: httpx.Client):
    url = f"/v1/api/portfolio/{ACCOUNT_ID}/summary"
    response = _get_response(client, url)
    data = response.json()

    print(response.headers)

    assert response.headers["content-type"] == "application/json; charset=utf-8"

    assert isinstance(data, dict)
    for key in ("accountcode", "acctid", "currency"):
        if isinstance(data, dict):
            break

    if isinstance(data, list) and data:
        first = data[0]
        assert isinstance(first, dict)

    if isinstance(data, dict) and "accountcode" in data:
        assert str(data["accountcode"]["value"]) == ACCOUNT_ID


@pytest.mark.integration
def test_portfolio_allocation_three_calls(client: httpx.Client):
    url = f"/v1/api/portfolio/{ACCOUNT_ID}/allocation"
    # Call 3 times with 0.5 s spacing to respect pacing limits.
    payloads = []
    for _ in range(3):
        payloads.append(_get_response(client, url).json())
        time.sleep(0.5)

    for p in payloads:
        assert isinstance(p, (dict, list))


@pytest.mark.integration
def test_invalid(client: httpx.Client):
    url = "/invalid"
    response = _get_response(client, url)
    data = response.json()

    assert isinstance(data, dict)
    assert data.get("error") == "Upstream service error."
    assert data.get("upstream_status") == 404
    assert "File not found" in data.get("detail", "")

    assert response.headers["content-type"] == "application/json"


@pytest.mark.integration
@pytest.mark.seldom
# Has a slower rate limit. If called too frequently, it will be rate limited.
@pytest.mark.skip(reason="Enable when you want to exercise slower-paced endpoint.")
def test_iserver_accounts(client: httpx.Client):
    url = "/v1/api/iserver/accounts"
    data = _get_response(client, url).json()
    assert isinstance(data, (dict, list))
    if isinstance(data, list) and data:
        assert isinstance(data[0], dict)
