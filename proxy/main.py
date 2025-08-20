import argparse
import asyncio
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
from curlify2 import Curlify
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from .const import API_HOST, API_PORT, EXTERNAL_API_BASE, HEADERS, VERSION
from .util import logging_level

LOGGING_CONFIG_PATH = Path(__file__).parent / "logging" / "logging.yaml"

with open(LOGGING_CONFIG_PATH) as f:
    LOGGING_CONFIG = yaml.safe_load(f)

# TICKLE LOOP ==================================================================

# These are initialised in main().
#
auth: Optional[ibauth.IBKROAuthFlow] = None
tickle_task = None

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
    global tickle_task
    tickle_task = asyncio.create_task(tickle_loop())
    yield
    tickle_task.cancel()
    try:
        await tickle_task
    except asyncio.CancelledError:
        pass


# ==============================================================================

app = FastAPI(title="IBKR Proxy Service", version=VERSION, lifespan=lifespan)


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])  # type: ignore[misc]
async def proxy(path: str, request: Request) -> Response:
    logging.info("🔵 Received request.")
    method = request.method
    url = urljoin(EXTERNAL_API_BASE, path)
    logging.debug(f"- Method:  {method}")
    logging.debug(f"- URL:     {url}")

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
            response = await client.request(
                method=method, url=url, content=body, headers={**headers, **HEADERS}, params=params, timeout=30.0
            )

        logging.debug("- " + Curlify(response.request).to_curl())

        headers = dict(response.headers)
        # Remove headers from response. These will be replaced with correct values.
        headers.pop("content-length", None)
        headers.pop("content-encoding", None)

        logging.info("✅ Return response.")
        print("=====================================================================")
        print(response.content)
        print(response.headers)
        print("=====================================================================")
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

    print(auth.bearer_token)

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
