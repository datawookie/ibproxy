import argparse
import time

import httpx

PROXY_HOST = "http://127.0.0.1"
PROXY_PORT = 9000


def request(path: str) -> httpx.Response:
    response = httpx.get(f"{PROXY_HOST}:{PROXY_PORT}/v1/api{path}")
    response.raise_for_status()
    return response


def main() -> None:
    request("/iserver/accounts")
    request("/portfolio/subaccounts")
    request("/fyi/notifications")
    request("/fyi/settings")

    time.sleep(5)

    for i in range(3):
        request("/trsrv/stocks?symbols=AAPL")
        request("/trsrv/futures?symbols=ES")
        time.sleep(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stress test the IBKR Proxy.")
    args = parser.parse_args()

    main()
