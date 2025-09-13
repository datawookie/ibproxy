import argparse
import asyncio
import bz2
import json
import logging
import logging.config
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import httpx
import ibauth
import uvicorn
import yaml
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from ibauth.timing import timing

from . import rate
from .const import API_HOST, API_PORT, HEADERS, JOURNAL_DIR, VERSION
from .middleware.request_id import RequestIdMiddleware
from .models import Health
from .status import router as status_router
from .tickle import log_status, tickle_loop
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
auth: Optional[ibauth.IBAuth] = None
tickle = None
TICKLE_MODE: Optional[str] = None

# ==============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global tickle

    def _tickle_done(task: asyncio.Task[None]) -> None:
        if task.cancelled():
            logging.info("Tickle task was cancelled.")
            return
        error = task.exception()
        if error:
            logging.exception("Tickle task terminated with exception: %s", error)

    tickle = asyncio.create_task(tickle_loop(auth, TICKLE_MODE))
    tickle.add_done_callback(_tickle_done)

    yield
    tickle.cancel()
    try:
        await tickle
    except asyncio.CancelledError:
        pass


# ==============================================================================

app = FastAPI(title="IBKR Proxy Service", version=VERSION, lifespan=lifespan)

app.include_router(status_router, prefix="/status", tags=["system"])

app.add_middleware(RequestIdMiddleware)


@app.get(
    "/health",
    tags=["system"],
    summary="Proxy Health Check",
    description="Retrieve the health status of the proxy.",
    response_model=Health,
)  # type: ignore[misc]
async def health() -> Health:
    result = {"status": "degraded"}
    if auth is not None:
        if not auth.authenticated:
            result = {"status": "not authenticated"}
        elif getattr(auth, "bearer_token", None):
            result = {"status": "ok"}

    return Health(**result)


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])  # type: ignore[misc]
async def proxy(path: str, request: Request) -> Response:
    method = request.method
    url = urljoin(f"https://{auth.domain}/", path)  # type: ignore[union-attr]
    logging.info(f"🔵 Request: [{request.state.request_id}] {method} {url}")

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

        headers["Authorization"] = f"Bearer {auth.bearer_token}"  # type: ignore[union-attr]

        # Forward request.
        async with httpx.AsyncClient() as client:
            now = rate.record(path)
            with timing() as duration:
                response = await client.request(
                    method=method,
                    url=url,
                    content=body,
                    headers={**headers, **HEADERS},
                    params=params,
                    timeout=30.0,
                )
            logging.info(f"⏳ Duration: {duration.duration:.3f} s")

        headers = dict(response.headers)
        # Remove headers from response. These will be replaced with correct values.
        headers.pop("content-length", None)
        headers.pop("content-encoding", None)

        # TODO: Could try to infer content type if header is missing.
        content_type = headers.get("content-type")

        logging.info(f"⌚ Rates (last {rate.WINDOW} s):")
        rps, period = rate.rate(path)
        logging.info(f"  - {rate.format(rps)} Hz / {rate.format(period)} s | {path}")
        rps, period = rate.rate()
        logging.info(f"  - {rate.format(rps)} Hz / {rate.format(period)} s | (global)")

        json_path = JOURNAL_DIR / (
            filename := now.strftime(f"%Y%m%d/%Y%m%d-%H%M%S-{request.state.request_id}.json.bz2")
        )
        #
        json_path.parent.mkdir(parents=True, exist_ok=True)

        def _write_journal() -> None:
            """
            Write request/response journal to a compressed JSON file.

            This is a blocking function so it needs to be run in a separate thread.
            """
            if not content_type:
                logging.warning("🚨 No content type in response!")
            if content_type and content_type.startswith("application/json"):
                data = response.json()
            else:
                data = response.text

            with bz2.open(json_path, "wt", encoding="utf-8") as f:
                logging.info(f"💾 Dump: {filename}.")
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

        await asyncio.to_thread(_write_journal)

        if response.is_error:
            # Upstream responded with 4xx/5xx status.
            upstream_status = response.status_code
            logging.error(
                "🚨 Upstream API error %s: %s %s.",
                upstream_status,
                method,
                url,
            )
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
            logging.info("✅ Return response.")
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=headers,
                media_type=content_type,
            )
    except httpx.RequestError as error:
        return JSONResponse(status_code=502, content={"error": f"Proxy error: {str(error)}"})


def main() -> None:
    global auth

    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true", help="Debugging mode.")
    parser.add_argument(
        "--config", type=str, default="config.yaml", help="Path to the configuration file (default: config.yaml)."
    )
    parser.add_argument("--port", type=int, default=None, help=f"Port to run the API server on (default: {API_PORT}).")
    parser.add_argument(
        "--tickle-mode",
        choices=["always", "auto", "off"],
        default="always",
        help="How the tickle loop decides to call auth.tickle(): "
        "'always' = ignore activity and call every interval (default), "
        "'auto' = call only when idle, "
        "'off' = don't run the tickle loop.",
    )
    args = parser.parse_args()

    if args.debug:
        LOGGING_CONFIG["root"]["level"] = "DEBUG"  # pragma: no cover

    logging.config.dictConfig(LOGGING_CONFIG)

    asyncio.run(log_status())
    try:
        auth = ibauth.auth_from_yaml(args.config)
    except Exception:
        logging.error("🚨 Authentication failed!")
        sys.exit(1)

    global TICKLE_MODE
    TICKLE_MODE = args.tickle_mode

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

    auth.logout()


if __name__ == "__main__":  # pragma: no cover
    main()
