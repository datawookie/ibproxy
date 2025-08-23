import argparse
import asyncio
import bz2
import json
import logging
import logging.config
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

from . import rate
from .const import API_HOST, API_PORT, HEADERS, JOURNAL_DIR, VERSION
from .timing import timing
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
auth: Optional[ibauth.IBKROAuthFlow] = None
tickle = None

# TICKLE LOOP ==================================================================

# Seconds between tickling the IBKR API.
#
TICKLE_INTERVAL = 10


async def tickle_loop() -> None:
    """Periodically call auth.tickle() while the app is running."""
    while True:
        if auth is not None:
            try:
                auth.tickle()
            except Exception as e:
                logging.error(f"Tickle failed: {e}")
        await asyncio.sleep(TICKLE_INTERVAL)


# ==============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global tickle
    tickle = asyncio.create_task(tickle_loop())
    yield
    tickle.cancel()
    try:
        await tickle
    except asyncio.CancelledError:
        pass


# ==============================================================================

app = FastAPI(title="IBKR Proxy Service", version=VERSION, lifespan=lifespan)


@app.get("/health", tags=["system"])  # type: ignore[misc]
async def health() -> dict[str, str]:
    if auth is not None and getattr(auth, "bearer_token", None):
        return {"status": "ok"}
    return {"status": "degraded"}


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])  # type: ignore[misc]
async def proxy(path: str, request: Request) -> Response:
    method = request.method
    url = urljoin(f"https://{auth.domain}/", path)  # type: ignore[union-attr]
    logging.info(f"🔵 Request: {method} {url}")

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
            logging.debug("- Headers:")
            for k, v in headers.items():
                logging.debug(f"  - {k}: {v}")
            logging.debug("- Params:")
            for k, v in params.items():
                logging.debug(f"  - {k}: {v}")

        headers["Authorization"] = f"Bearer {auth.bearer_token}"  # type: ignore[union-attr]

        # Forward request.
        async with httpx.AsyncClient() as client:
            now = rate.record(path)
            with timing() as duration:
                response = await client.request(
                    method=method, url=url, content=body, headers={**headers, **HEADERS}, params=params, timeout=30.0
                )
            response.raise_for_status()
            logging.info(f"⏳ Duration: {duration.duration:.3f} s")

        headers = dict(response.headers)
        # Remove headers from response. These will be replaced with correct values.
        headers.pop("content-length", None)
        headers.pop("content-encoding", None)

        logging.info(f"⌚ Rates (last {rate.WINDOW} s):")
        rps, period = rate.rate(path)
        logging.info(f"  - {rate.format(rps)} Hz / {rate.format(period)} s | {path}")
        rps, period = rate.rate()
        logging.info(f"  - {rate.format(rps)} Hz / {rate.format(period)} s | (global)")

        json_path = JOURNAL_DIR / (filename := now.strftime("%Y%m%d/%Y%m%d-%H%M%S:%f.json.bz2"))
        #
        json_path.parent.mkdir(parents=True, exist_ok=True)
        #
        with bz2.open(json_path, "wt", encoding="utf-8") as f:
            logging.info(f"💾 Dump: {filename}.")
            dump = {
                "request": {
                    "url": url,
                    "method": method,
                    "headers": headers,
                    "body": json.loads(body.decode("utf-8")) if body else None,
                },
                "response": response.json(),
                "duration": duration.duration,
            }
            json.dump(dump, f, indent=2)

        logging.info("✅ Return response.")
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=headers,
            media_type=headers.get("content-type", "application/json"),
        )

    except httpx.RequestError as e:
        return JSONResponse(status_code=502, content={"error": f"Proxy error: {str(e)}"})


def main() -> None:
    global auth

    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true", help="Debugging mode.")
    args = parser.parse_args()

    if args.debug:
        LOGGING_CONFIG["root"]["level"] = "DEBUG"

    logging.config.dictConfig(LOGGING_CONFIG)

    auth = ibauth.auth_from_yaml("config.yaml")

    auth.get_access_token()
    auth.get_bearer_token()

    auth.ssodh_init()
    auth.validate_sso()

    uvicorn.run(
        "proxy.main:app",
        host=API_HOST,
        port=API_PORT,
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
