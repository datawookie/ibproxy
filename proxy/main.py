import argparse
from fastapi import FastAPI, HTTPException
import asyncio
import logging
from pathlib import Path

import uvicorn
import yaml

import ibkr_oauth_flow

from .const import VERSION, API_HOST, API_PORT

LOGGING_CONFIG_PATH = Path(__file__).parent / "logging" / "logging.yaml"

with open(LOGGING_CONFIG_PATH) as f:
    LOGGING_CONFIG = yaml.safe_load(f)

app = FastAPI(title="IBKR Proxy Service", version=VERSION)

# TICKLE LOOP ==================================================================

# These are initialised in main().
#
auth = None
tickle_task = None

# Seconds between tickling the IBKR API.
#
TICKLE_INTERVAL = 10

async def tickle_loop():
    """Periodically call auth.tickle() while the app is running."""
    while True:
        try:
            auth.tickle()
        except Exception as e:
            logging.error(f"Tickle failed: {e}")
        await asyncio.sleep(TICKLE_INTERVAL)

# ==============================================================================

@app.on_event("startup")
async def startup_event():
    global tickle_task
    tickle_task = asyncio.create_task(tickle_loop())


@app.on_event("shutdown")
async def shutdown_event():
    global tickle_task
    if tickle_task:
        tickle_task.cancel()
        try:
            await tickle_task
        except asyncio.CancelledError:
            pass

# ==============================================================================

def main():
    global auth

    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true", help="Debugging mode.")
    args = parser.parse_args()

    if args.debug:
        LOGGING_CONFIG["root"]["level"] = "DEBUG"

    logging.config.dictConfig(LOGGING_CONFIG)

    auth = ibkr_oauth_flow.auth_from_yaml("config.yaml")

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