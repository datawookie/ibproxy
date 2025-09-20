# IBKR Proxy

![PyPI - Version](https://img.shields.io/pypi/v/ibproxy)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/ibproxy)](https://pypi.org/project/ibproxy/)
![Codecov](https://img.shields.io/codecov/c/github/datawookie/ibproxy)

## Setup

You need to have the following files in the local directory to enable the use of
the IBKR OAuth service:

- `config.yaml` and
- `privatekey.pem`.

See the `README` for the [`ibauth`](https://github.com/datawookie/ibauth) project for documentation of the `config.yaml`
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

There are ways that you can expose the proxy to the outside world. For the purpose of illustration suppose that you are running the proxy on an EC2
instance at 3.218.141.190.

### NGINX

Unless you set up authentication this would definitely open up a can of worms.

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

### Local IBKR Authentication Workflow

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
