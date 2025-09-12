# IBKR Proxy

[![codecov](https://codecov.io/gh/datawookie/ibproxy/branch/master/graph/badge.svg)](https://codecov.io/gh/datawookie/ibproxy)

```python
import json
import time

import httpx

if __name__ == "__main__":
    headers = {
        "Accept-Encoding": "gzip,deflate",
        "Accept": "*/*",
        "Connection": "keep-alive",
        "User-Agent": "OAuth",
    }

    account_id = "DUH999999"

    url = f"http://127.0.0.1:9000/v1/api/portfolio/{account_id}/summary"

    response = httpx.get(url, headers=headers, verify=False, timeout=5)
    response.raise_for_status()

    data = response.json()

    print(json.dumps(data["accountcode"], indent=2))

    url = f"http://127.0.0.1:9000/v1/api/portfolio/{account_id}/allocation"

    for _ in range(3):
        response = httpx.get(url, headers=headers, verify=False, timeout=5)
        response.raise_for_status()

        time.sleep(0.5)
```

You can also hit the proxy from the command line:

```bash
curl http://127.0.0.1:9000/v1/api/iserver/accounts
```

## Setup

You need to have the following files in the local directory to enable the use of
the IBKR OAuth service:

- `config.yaml` and
- `privatekey.pem`.

See the `README` for the `ibauth` project for documentation of the `config.yaml`
content.

## Running Locally

```bash
uv sync
uv run ibproxy --debug
```

## Running on EC2

To run on an EC2 instance you'd do precisely the same thing as for running
locally. Since the proxy is configured to only answer requests from `localhost`
this will mean that requests from outside will not reach the proxy. In general
this is a good thing.

For the purpose of illustration suppose that you are running the proxy on an EC2
instance at 3.218.141.190.

There are ways that you can expose the proxy to the outside world.

### NGINX

Unless you set up authentication on the proxy this would potentially open up a
can of worms.

### SSH Tunnel

This is a simple and secure approach. Presumably you have SSH access to the EC2
instance. Run the following on your local machine to set up an SSH tunnel to the
EC2 instance:

```bash
ssh -N -L 9000:127.0.0.1:9000 ubuntu@3.218.141.190
```

That will connect port 9000 on your local machine to port 9000 on the EC2
instance. Local requests on port 9000 will then be relayed via the secure tunnel
to the proxy on the EC2 instance.

## Development

```bash
uv sync
uv run ibproxy --debug
```

You can access the Swagger interface at http://127.0.0.1:9000/docs.

If you are testing changes to `ibauth` then you can install a local copy.

1. Add this to the end of `pyproject.toml`:

    ```
    [tool.uv.sources]
    ibauth = { path = "../ibauth", editable = true }
    ```

2. `uv lock --upgrade`
3. `uv sync`

You can also set this up in one quick move:

```bash
uv add --editable ../ibauth
```

## API Error Codes

- `500` `Please query /accounts first`
- `401` `not authenticated`
- `400` `Bad Request: no bridge`
