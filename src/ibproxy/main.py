import argparse
import asyncio
import bz2
import json
import logging
import logging.config
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin

import httpx
import ibauth
import uvicorn
import yaml
from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, Response
from ibauth.timing import AsyncTimer

from . import rate
from .const import API_HOST, API_PORT, HEADERS, JOURNAL_DIR, VERSION
from .middleware.request_id import RequestIdMiddleware
from .rate import enforce_rate_limit, rate_loop
from .system import router as system_router
from .tickle import TICKLE_INTERVAL, TickleMode, tickle_loop
from .util import logging_level

LOGGING_CONFIG_PATH = Path(__file__).parent / "logging" / "logging.yaml"

with open(LOGGING_CONFIG_PATH) as f:
    LOGGING_CONFIG = yaml.safe_load(f)

import warnings

warnings.filterwarnings(
    "ignore",
    message="Duplicate Operation ID.*",
    module="fastapi.openapi.utils",
)

# GLOBALS ======================================================================

# These are initialised in main().
#
tickle = None
TICKLE_MODE: TickleMode = TickleMode.ALWAYS

# ==============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global tickle

    # Event which is set during a reset.
    #
    # This uses the Gatekeeper Pattern to block new requests while a reset is in progress.
    #
    # The event is lightweight. It simply manages list of paused coroutines.
    #
    app.state.gate = asyncio.Event()
    app.state.gate.set()

    app.state.started_at = datetime.now(UTC)

    def _tickle_done(task: asyncio.Task[None]) -> None:
        if task.cancelled():
            logging.info("Tickle task was cancelled.")
            return
        error = task.exception()
        if error:
            logging.exception("Tickle task terminated with exception: %s", error)

    app.state.auth = ibauth.auth_from_yaml(app.state.args.config)
    app.state.client = httpx.AsyncClient(
        timeout=30.0,
        # TODO: Tune the connection limits for traffic profile.
        limits=httpx.Limits(max_keepalive_connections=100, max_connections=200),
    )
    try:
        await app.state.auth.connect()
    except Exception:
        logging.error("🚨 Authentication failed!")

    tickle = asyncio.create_task(tickle_loop(app))
    tickle.add_done_callback(_tickle_done)

    rate = asyncio.create_task(rate_loop())

    yield
    tickle.cancel()
    rate.cancel()
    try:
        await tickle
    except:
        # Normally this will be triggered by asyncio.CancelledError in the
        # tickle loop. But if something breaks then the exception should be
        # logged in the done callback (and we also end up here).
        #
        # Will be called after the done callback has run.
        pass
    try:
        await rate
    except:
        pass

    await app.state.client.aclose()
    await app.state.auth.logout()


# ==============================================================================

app = FastAPI(title="IBKR Proxy Service", version=VERSION, lifespan=lifespan)

app.include_router(system_router)

app.add_middleware(RequestIdMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=100, compresslevel=5)


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])  # type: ignore[untyped-decorator]
async def proxy(path: str, request: Request) -> Response:
    id: str = request.state.request_id

    # Enforce rate limit.
    #
    await enforce_rate_limit(id)

    # Check if the gate is open. If it is then this will return immediately. If not then
    # it will wait until the gate is opened again.
    #
    await request.app.state.gate.wait()

    method = request.method
    url = urljoin(f"https://{request.app.state.auth.domain}/", path)
    logging.info(f"🔵 [{id}] Request: {method} {url}")

    try:
        # Get body, parameters and headers from request.
        body = await request.body()
        params = dict(request.query_params)
        headers = dict(request.headers)

        # Remove host header because this will reference the proxy rather than
        # the target site.
        #
        headers.pop("host")

        if body:
            logging.debug(f"- Body:    {body}")
        if logging_level() <= logging.DEBUG:
            if headers:
                logging.debug("- Headers:")
                for k, v in headers.items():
                    logging.debug(f"  - {k}: {v}")
            if params:
                logging.debug("- Params:")
                for k, v in params.items():
                    logging.debug(f"  - {k}: {v}")

        headers["Authorization"] = f"Bearer {request.app.state.auth.bearer_token}"

        # Forward request.
        now = await rate.record(path)
        async with AsyncTimer() as duration:
            response = await request.app.state.client.request(
                method=method,
                url=url,
                content=body,
                headers={**headers, **HEADERS},
                params=params,
            )
        logging.info(f"⏳ [{id}] Duration: {duration.duration:.3f} s")

        headers = dict(response.headers)
        # Remove headers from response. These will be replaced with correct values.
        headers.pop("content-length", None)
        headers.pop("content-encoding", None)

        # TODO: Could try to infer content type if header is missing.
        content_type = headers.get("content-type")

        # Ensure a content-length header is present if upstream didn't supply one.
        # This keeps tests and some clients happy when we strip upstream headers.
        if "content-length" not in headers:
            headers["content-length"] = str(len(response.content))

        def _write_journal() -> None:
            """
            Write request/response journal to a compressed JSON file.

            This is a blocking function so it needs to be run in a separate thread.
            """
            json_path = JOURNAL_DIR / (
                filename := now.strftime(f"%Y%m%d/%Y%m%d-%H%M%S-{request.state.request_id}.json.bz2")
            )
            #
            json_path.parent.mkdir(parents=True, exist_ok=True)

            if not content_type:
                logging.warning("🚨 No content type in response!")
            if content_type and content_type.startswith("application/json"):
                data = response.json()
            else:
                data = response.text

            with bz2.open(json_path, "wt", encoding="utf-8") as f:
                logging.info(f"💾 [{id}] Dump: {filename}.")
                dump = {
                    "request": {
                        "id": request.state.request_id,
                        "url": url,
                        "method": method,
                        "headers": dict(response.request.headers),
                        "params": params,
                        "body": json.loads(body.decode("utf-8")) if body else None,
                    },
                    "response": {
                        "status_code": response.status_code,
                        "data": data,
                    },
                    "duration": duration.duration,
                }
                json.dump(dump, f, indent=2)

        if JOURNAL_DIR:
            await asyncio.to_thread(_write_journal)

        if response.is_error:
            # Upstream responded with 4xx/5xx status.
            upstream_status = response.status_code
            logging.error(f"🚨 [{id}] Upstream API error {upstream_status}: {method} {url}.")
            # Return a proxied error to caller (don't leak stack trace).
            return JSONResponse(
                content={
                    "error": "Upstream service error.",
                    "upstream_status": upstream_status,
                    "detail": response.text,
                },
                # HTTP 502 Bad Gateway error indicates a server-side
                # communication issue where a gateway or proxy received an
                # invalid response from an upstream server
                status_code=502,
            )
        else:
            logging.info(f"✅ [{id}] Return response.")
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=headers,
                media_type=content_type,
            )
    except httpx.RequestError as error:
        return JSONResponse(status_code=502, content={"error": f"Proxy error: {str(error)}"})


def main() -> None:
    global app

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Debugging mode.",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="Path to the configuration file (default: config.yaml).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"Port to run the API server on (default: {API_PORT}).",
    )
    parser.add_argument(
        "--tickle-mode",
        choices=[mode.value for mode in TickleMode],
        default=TickleMode.ALWAYS.value,
        help="How the tickle loop decides to call auth.tickle(): "
        "'always' = ignore activity and call every interval (default), "
        "'auto' = call only when idle, "
        "'off' = don't run the tickle loop.",
    )
    parser.add_argument(
        "--tickle-interval",
        type=float,
        default=TICKLE_INTERVAL,
        help=f"Interval (seconds) between tickles (default: {TICKLE_INTERVAL}).",
    )
    parser.add_argument(
        "--disable-journal",
        action="store_true",
        help="Disable writing details of each request/response to a compressed JSON file.",
    )
    args = parser.parse_args()

    app.state.args = args

    if args.debug:
        LOGGING_CONFIG["root"]["level"] = "DEBUG"  # pragma: no cover
        LOGGING_CONFIG["loggers"]["ibauth"]["level"] = "DEBUG"  # pragma: no cover

    if args.disable_journal:
        global JOURNAL_DIR
        JOURNAL_DIR = None  # type: ignore[assignment]

    logging.config.dictConfig(LOGGING_CONFIG)

    logging.info("=" * 69)
    logging.info(f"ibproxy ({VERSION})")
    logging.info("=" * 69)

    uvicorn.run(
        "ibproxy.main:app",
        host=API_HOST,
        port=args.port or API_PORT,
        #
        # Can only have a single worker and cannot support reload.
        #
        # This is because we can only have a single connection to the IBKR API.
        #
        workers=1,
        reload=False,
        #
        log_config=LOGGING_CONFIG,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
