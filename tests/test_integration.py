import os
import time
from typing import Any, Dict

import httpx
import pytest
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

PROXY_URL = os.getenv("PROXY_URL", "http://127.0.0.1:9000")
ACCOUNT_ID = os.getenv("IBKR_ACCOUNT_ID", "DUH638336")

DEFAULT_HEADERS = {
    "Accept": "*/*",
    "Connection": "keep-alive",
    "User-Agent": "ibproxy-integration-test",
    "Accept-Encoding": "gzip,deflate",
}

REQUEST_TIMEOUT = 5.0


@retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(0.25),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
def _get_json(client: httpx.Client, url: str) -> Dict[str, Any]:
    resp = client.get(url, headers=DEFAULT_HEADERS)
    resp.raise_for_status()
    return resp.json()


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
    data = _get_json(client, url)

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
        payloads.append(_get_json(client, url))
        time.sleep(0.5)

    for p in payloads:
        assert isinstance(p, (dict, list))


@pytest.mark.integration
@pytest.mark.seldom
# Has a slower rate limit. If called too frequently, it will be rate limited.
@pytest.mark.skip(reason="Enable when you want to exercise slower-paced endpoint.")
def test_iserver_accounts(client: httpx.Client):
    url = "/v1/api/iserver/accounts"
    data = _get_json(client, url)
    assert isinstance(data, (dict, list))
    if isinstance(data, list) and data:
        assert isinstance(data[0], dict)
