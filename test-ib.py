import json
import logging
import time

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

if __name__ == "__main__":
    headers = {
        "Accept-Encoding": "gzip,deflate",
        "Accept": "*/*",
        "Connection": "keep-alive",
        "User-Agent": "OAuth",
    }

    account_id = "DUH638336"

    # ==========================================================================

    url = f"http://127.0.0.1:9000/v1/api/portfolio/{account_id}/summary"

    response = httpx.get(url, headers=headers, verify=False)
    response.raise_for_status()

    data = response.json()

    print(json.dumps(data["accountcode"], indent=2))

    # ==========================================================================

    url = f"http://127.0.0.1:9000/v1/api/portfolio/{account_id}/allocation"

    for _ in range(3):
        response = httpx.get(url, headers=headers, verify=False)
        response.raise_for_status()

        time.sleep(0.5)

    # ==========================================================================

    # This has a slower rate limit. If it is called too frequently, it will be rate limited.

    # url = "http://127.0.0.1:9000/v1/api/iserver/accounts"

    # response = httpx.get(url, headers=headers, verify=False)
    # response.raise_for_status()

    # data = response.json()

    # print(json.dumps(data, indent=2))

    # ==========================================================================
