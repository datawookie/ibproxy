import argparse
from fastapi import FastAPI, HTTPException
import asyncio
import logging
from pathlib import Path
import time

import uvicorn
import yaml

import ibkr_oauth_flow

from .const import VERSION, API_HOST, API_PORT, WORKERS

# logging.basicConfig(level=logging.INFO)

LOGGING_CONFIG_PATH = Path(__file__).parent / "logging" / "logging.yaml"

with open(LOGGING_CONFIG_PATH) as f:
    LOGGING_CONFIG = yaml.safe_load(f)

# # Global IBKR connection
# ib = IB()

# @app.on_event("startup")
# async def startup_event():
#     """Connect to IBKR when the app starts."""
#     try:
#         logging.info("Connecting to IBKR...")
#         await asyncio.get_event_loop().run_in_executor(
#             None, lambda: ib.connect("127.0.0.1", 7497, clientId=1)
#         )
#         logging.info("Connected to IBKR.")
#     except Exception as e:
#         logging.error(f"Could not connect to IBKR: {e}")
#         raise

# @app.on_event("shutdown")
# async def shutdown_event():
#     """Disconnect from IBKR when the app stops."""
#     logging.info("Disconnecting from IBKR...")
#     await asyncio.get_event_loop().run_in_executor(None, ib.disconnect)

# @app.get("/market_data/{symbol}")
# async def get_market_data(symbol: str):
#     """Fetch market data for a given symbol."""
#     try:
#         contract = Stock(symbol.upper(), "SMART", "USD")
#         ticker = ib.reqMktData(contract, "", False, False)

#         # Give IBKR some time to respond
#         await asyncio.sleep(1)

#         return {
#             "symbol": symbol.upper(),
#             "bid": ticker.bid,
#             "ask": ticker.ask,
#             "last": ticker.last
#         }
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))

app = FastAPI(title="IBKR Proxy Service", version=VERSION)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true", help="Debugging mode.")
    parser.add_argument("--no-reload", action="store_true", help="Don't reload (for production).")
    args = parser.parse_args()

    if args.debug:
        LOGGING_CONFIG["root"]["level"] = "DEBUG"

    logging.config.dictConfig(LOGGING_CONFIG)

    auth = ibkr_oauth_flow.auth_from_yaml("config.yaml")

    auth.get_access_token()
    auth.get_bearer_token()

    auth.ssodh_init()
    auth.validate_sso()

    # # This will keep session alive.
    # for _ in range(3):
    #     auth.tickle()
    #     time.sleep(10)

    uvicorn.run(
        "proxy.main:app",
        host=API_HOST,
        port=API_PORT,
        workers=WORKERS,
        reload=not args.no_reload,
        log_config=LOGGING_CONFIG,
    )

    auth.logout()


if __name__ == "__main__":  # pragma: no cover
    main()