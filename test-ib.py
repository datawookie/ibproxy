import json
import logging

import httpx
import ibauth

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

if __name__ == "__main__":
    auth = ibauth.auth_from_yaml("config.yaml")

    auth.get_access_token()
    auth.get_bearer_token()

    auth.ssodh_init()
    auth.validate_sso()

    bearer_token = auth.bearer_token

    headers = {
        "Accept-Encoding": "gzip,deflate",
        "Authorization": f"Bearer {bearer_token}",
        "Accept": "*/*",
        "Connection": "keep-alive",
        "User-Agent": "OAuth",
    }

    account_id = "DUH638336"

    # DIRECT REQUEST ===========================================================

    url = f"{auth.url_client_portal}/v1/api/portfolio/{account_id}/summary"

    response = httpx.get(url, headers=headers, verify=False)
    response.raise_for_status()

    data = response.json()

    print(json.dumps(data["accountcode"], indent=2))

    # VIA PROXY ================================================================

    url = f"http://127.0.0.1:9000/v1/api/portfolio/{account_id}/summary"

    response = httpx.get(url, headers=headers, verify=False)
    response.raise_for_status()

    data = response.json()

    print(json.dumps(data["accountcode"], indent=2))

    # ==========================================================================

    auth.logout()
