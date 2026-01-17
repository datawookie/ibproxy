import gzip
import os
import time
from typing import Any

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


def _get_response(client: httpx.Client, url: str, headers: dict[str, str] = {}) -> dict[str, Any]:
    headers = {**DEFAULT_HEADERS, **headers}
    return client.get(url, headers=headers)


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

    assert "application/json" in response.headers["content-type"]

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


@pytest.mark.seldom
# Has a slower rate limit. If called too frequently, it will be rate limited.
@pytest.mark.skip(reason="Enable when you want to exercise slower-paced endpoint.")
def test_iserver_accounts(client: httpx.Client):
    url = "/v1/api/iserver/accounts"
    data = _get_response(client, url).json()
    assert isinstance(data, (dict, list))
    if isinstance(data, list) and data:
        assert isinstance(data[0], dict)


TICKER_LIST = [
    "AAPL",
    "MSFT",
    "GOOGL",
    "AMZN",
    "NVDA",
    "TSLA",
    "META",
    "BRK.B",
    "UNH",
    "LLY",
    "JPM",
    "V",
    "JNJ",
    "WMT",
    "XOM",
    "PG",
    "MA",
    "HD",
    "CVX",
    "MRK",
    "ABBV",
    "AVGO",
    "COST",
    "PEP",
    "KO",
    "BAC",
    "DIS",
    "ADBE",
    "TMO",
    "ORCL",
    "NFLX",
    "CRM",
    "INTC",
    "PFE",
    "ABT",
    "MCD",
    "CSCO",
    "DHR",
    "VZ",
    "NKE",
    "ACN",
    "WFC",
    "LIN",
    "TXN",
    "NEE",
    "MS",
    "AMD",
    "AMGN",
    "HON",
    "PM",
    "UNP",
    "UPS",
    "RTX",
    "BMY",
    "QCOM",
    "SBUX",
    "LOW",
    "CAT",
    "INTU",
    "IBM",
    "LMT",
    "BLK",
    "GS",
    "GE",
    "BA",
    "DE",
    "MDT",
    "T",
    "SPGI",
    "NOW",
    "PLD",
    "ZTS",
    "ISRG",
    "BKNG",
    "CB",
    "AMAT",
    "ADI",
    "MO",
    "VRTX",
    "REGN",
    "CI",
    "GILD",
    "SYK",
    "MU",
    "MMC",
    "APD",
    "PANW",
    "EL",
    "ADP",
    "FDX",
    "TGT",
    "SO",
    "EQIX",
    "ICE",
    "HCA",
    "SLB",
    "PGR",
    "CL",
    "EW",
    "NSC",
]


@pytest.mark.integration
def test_compression(client: httpx.Client):
    tickers = ",".join(TICKER_LIST)
    url = f"/v1/api/trsrv/stocks?symbols={tickers}"

    headers = {**DEFAULT_HEADERS}

    # Use stream() to access raw (uncompressed) response data.
    with client.stream("GET", url, headers=headers) as response:
        compressed = b"".join(response.iter_raw())

    decompressed = gzip.decompress(compressed)

    compressed_size = len(compressed)
    decompressed_size = len(decompressed)

    compression_ratio = decompressed_size / compressed_size

    assert compressed_size < decompressed_size
    assert compression_ratio > 5.0
    assert "gzip" in response.headers.get("Content-Encoding").lower()

    # Now without compression.
    headers["Accept-Encoding"] = "identity"
    with client.stream("GET", url, headers=headers) as response:
        assert response.headers.get("Content-Encoding") is None
        assert int(response.headers.get("Content-Length")) == decompressed_size
