# IBKR Proxy

## Setup

You need to have the following files in the local directory to enable the use of
the IBKR OAuth service:

- `config.yaml` and
- `privatekey.pem`.

## Development

```bash
uv sync
uv run ibproxy --debug
```

You can access the Swagger interface at http://127.0.0.1:9000/docs.
