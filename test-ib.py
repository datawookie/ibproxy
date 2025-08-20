import json
import logging

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

    # VIA PROXY ================================================================

    url = f"http://127.0.0.1:9000/v1/api/portfolio/{account_id}/summary"

    response = httpx.get(url, headers=headers, verify=False)
    response.raise_for_status()

    data = response.json()

    print(json.dumps(data["accountcode"], indent=2))

    # ==========================================================================
