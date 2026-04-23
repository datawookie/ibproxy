# AGENTS.md

## Purpose

`ibproxy` is a FastAPI-based local proxy in front of the Interactive Brokers Web API. It owns one authenticated IBKR session, forwards nearly all requests upstream, exposes a few local system endpoints, keeps the session alive with a background tickle loop, and records request rate plus optional request/response journals.

This file is for agents working in this repository. Read it before making changes.

## Environment

- Python: `>=3.12`
- Package manager / runner: `uv`
- Main entrypoint: `uv run ibproxy --debug`
- Required local files for real runs: `config.yaml` and `privatekey.pem`
- Default bind: `127.0.0.1:9000`
- Local API docs when running: `http://127.0.0.1:9000/docs`

Useful commands:

- `uv sync`
- `uv run ibproxy --debug`
- `uv run pytest -q`
- `uv run pytest -m integration`
- `uv run pytest -m seldom`
- `uv run ruff check .`
- `uv run mypy src`

Current observed baseline when this file was written:

- `uv run pytest -q` passes
- `uv run ruff check .` is not fully clean
- `uv run mypy src` is not fully clean

Do not assume lint/typecheck are green before your change. Verify the subset you touch.

## Repository Layout

- `src/ibproxy/main.py`: FastAPI app, lifespan setup/teardown, catch-all proxy route, CLI entrypoint.
- `src/ibproxy/system/`: local endpoints for `/status`, `/reset`, `/uptime`, `/health`.
- `src/ibproxy/tickle.py`: background keepalive loop and tickle mode logic.
- `src/ibproxy/rate/limit.py`: token-bucket style global rate limiter.
- `src/ibproxy/rate/log.py`: sliding-window request timestamp log and rate reporting.
- `src/ibproxy/middleware/request_id.py`: request ID middleware, adds `X-Request-ID`.
- `src/ibproxy/logging/`: logging config and rotating file handler.
- `src/ibproxy/models.py`: Pydantic response models.
- `src/stress.py`: simple manual traffic generator against a running proxy.
- `tests/`: unit tests plus proxy-backed integration tests.

## Runtime Architecture

### App lifecycle

`main.py` creates one global `FastAPI` app and uses a lifespan hook to initialize shared state:

- `app.state.gate`: `asyncio.Event` used to block new requests during reset.
- `app.state.started_at`: startup timestamp for `/uptime`.
- `app.state.auth`: IBKR auth/session object from `ibauth.auth_from_yaml(...)`.
- `app.state.client`: shared `httpx.AsyncClient`.
- background tasks:
  - `tickle_loop(app)`
  - `rate_loop()`

Shutdown cancels both tasks, closes the HTTP client, and logs out of IBKR.

### Proxy flow

The catch-all route in `main.py` handles almost all HTTP methods and forwards to the upstream IBKR host.

Important invariants:

- Every request must pass through `RequestIdMiddleware`.
- Every proxied request waits on `enforce_rate_limit(...)`.
- Every proxied request waits on `app.state.gate`; resets deliberately close this gate.
- The incoming `Host` header is stripped before forwarding.
- `Authorization: Bearer ...` is injected from `app.state.auth.bearer_token`.
- Upstream `content-length` and `content-encoding` are stripped and rebuilt locally.
- If upstream omits `content-length`, the proxy adds one based on `response.content`.
- Non-2xx/3xx upstream responses are mapped to a local `502` JSON error payload.
- Upstream `401` triggers a reconnect attempt via `_reconnect(...)`.

If you change forwarding behavior, preserve these guarantees unless the task explicitly changes them.

### Journaling

By default the proxy writes compressed request/response dumps under `journal/YYYYMMDD/...json.bz2`.

Notes:

- Journal writing happens in `asyncio.to_thread(...)` because it is blocking.
- `--disable-journal` disables the feature by setting `JOURNAL_DIR = None`.
- Tests rely on the journal filename embedding the generated request ID.

### Reset behavior

`src/ibproxy/system/reset.py` blocks new requests while reconnecting:

1. `state.gate.clear()`
2. `logout()`
3. poll until disconnected
4. `connect()`
5. fetch system status
6. `state.gate.set()` in `finally`

Do not remove the `finally` reopening of the gate. A failed reset must not leave the proxy permanently blocked.

### Tickle behavior

The tickle loop supports:

- `always`: tickle every interval
- `auto`: only tickle when recent request activity is older than the interval
- `off`: exit immediately

The loop also logs request-rate information and system metrics. Tests monkeypatch the status and metric helpers heavily, so keep those seams intact when refactoring.

### Rate limiting

There are two distinct rate mechanisms:

- `rate/limit.py`: global backpressure using a single leaky/token bucket
- `rate/log.py`: timestamp history per endpoint for observability and tickle decisions

Do not conflate them. The bucket enforces; the log records.

`rate.times` is global in-memory state. Tests usually clear it before and after each case.

## System Endpoints

These are mounted at the app root by `src/ibproxy/system/__init__.py`:

- `GET /health`
- `GET /status`
- `POST /reset`
- `GET /uptime`

Be aware that the catch-all proxy route also exists at root level. Route additions need to remain compatible with that setup.

## Testing Guidance

### Default test strategy

Run targeted tests first, then the full suite if your change is broad.

Examples:

- `uv run pytest -q tests/test_proxy.py`
- `uv run pytest -q tests/test_tickle.py`
- `uv run pytest -q tests/test_system_reset.py`
- `uv run pytest -q`

### Test structure and conventions

- `tests/conftest.py` disables real rate limiting for most tests.
- Tests replace the real tickle loop with a no-op when using `TestClient`.
- Tests patch `app.state.auth` directly instead of building a real IBKR session.
- Integration tests require a running proxy and are skipped if it is unreachable.
- Integration tests use `PROXY_URL` and `IBKR_ACCOUNT_ID` when provided.
- `pytest-socket` is enabled; network access is restricted by default.

When adding tests:

- Prefer monkeypatching `httpx.AsyncClient.request` for proxy route tests.
- Keep journal writes redirected to temp paths.
- Clear or control `ibproxy.rate.times` when asserting timing/rate logic.
- Use `freezegun` or monkeypatched clocks for deterministic timing.

## Logging and Observability

- Logging config lives in `src/ibproxy/logging/logging.yaml`.
- Production logging writes to stdout and a rotating `proxy.log`.
- `RequestIdMiddleware` is the only source of request IDs today.
- Some tests assert on specific log messages and emoji markers. Avoid unnecessary churn in log wording for existing paths.

## Editing Guidance

### When changing `main.py`

Be careful with:

- lifespan state initialization
- request gating
- upstream header normalization
- `401 -> reconnect` flow
- content handling for both JSON and non-JSON bodies
- journal filenames and dump schema

`main.py` is the highest-risk file in the repo. Small changes here often affect multiple tests.

### When changing `system/status.py`

This module scrapes IBKR HTML with BeautifulSoup. Parsing is intentionally narrow and tested using a minimal HTML fixture. If IBKR page structure changes, update both parser and tests together.

### When changing rate logic

Preserve the distinction between:

- hard request throttling in `limit.py`
- historical request timestamps in `log.py`

Tests assume `ibproxy.rate.WINDOW` can be monkeypatched and that `ibproxy.rate.times` remains module-level shared state.

### When changing middleware

The request ID is propagated through logging, journal filenames, and the `X-Request-ID` response header. Changes here have broad surface area.

## Packaging and Release Notes

- Packaging metadata is in `pyproject.toml`.
- `Makefile` has a `deploy` target that only allows publish from the `master` branch.
- CLI scripts:
  - `ibproxy = ibproxy.main:main`
  - `stress = stress:main`

## Change Checklist

Before finishing a task:

1. Run the narrowest relevant tests.
2. Run `uv run pytest -q` if the change crosses module boundaries.
3. Mention any skipped integration/seldom tests explicitly.
4. Call out any lint or mypy issues you introduced versus pre-existing baseline.
5. If you changed request forwarding, reset logic, journaling, or tickle behavior, say so clearly in the summary.
