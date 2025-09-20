import asyncio
import logging
from datetime import datetime
from typing import Optional

import httpx
import ibauth

from . import rate
from .const import DATETIME_FMT
from .status import get_system_status

# Seconds between tickling the IBKR API.
#
TICKLE_INTERVAL = 120
TICKLE_MIN_SLEEP = 5


async def log_status() -> None:
    try:
        status = await asyncio.wait_for(get_system_status(), timeout=10.0)
    except (asyncio.TimeoutError, httpx.ConnectTimeout):
        logging.warning("🚧 IBKR status timed out!")
    except RuntimeError as error:
        logging.error(error)
    else:
        logging.info("IBKR status: %s %s", status.colour, status.label)


async def tickle(auth: ibauth.IBAuth) -> None:
    """
    The .tickle() method is blocking, so run it in a thread.
    """
    # TODO: Refactor ibauth so that it's async?
    # await asyncio.to_thread(auth.tickle)
    await auth.tickle()


async def tickle_loop(auth: Optional[ibauth.IBAuth], mode: Optional[str] = "always") -> None:
    """Periodically call auth.tickle() while the app is running."""
    if mode == "off":
        logging.warning("⛔ Tickle loop disabled.")
        return

    # Initial value for interval between tickles.
    sleep: float = TICKLE_INTERVAL

    logging.info("🔁 Start tickle loop (mode=%s).", mode)
    while True:
        logging.debug("⏳ Sleep: %.1f s", sleep)
        await asyncio.sleep(sleep)

        # Reset sleep to default interval (can be adjusted below).
        sleep = TICKLE_INTERVAL

        try:
            await log_status()

            if auth is not None:
                if mode == "always":
                    await tickle(auth)
                else:
                    if latest := rate.latest():
                        logging.info(" - Latest request: %s", datetime.fromtimestamp(latest).strftime(DATETIME_FMT))
                        delay = datetime.now().timestamp() - latest
                        if delay < TICKLE_INTERVAL:
                            logging.info("- Within tickle interval. No need to tickle again.")
                            sleep -= delay
                            sleep = max(sleep, TICKLE_MIN_SLEEP)
                        else:
                            await tickle(auth)
                    else:
                        await tickle(auth)
        except Exception:
            logging.error("🚨 Tickle failed. Will retry after short delay.")
            # Backoff a bit so repeated failures don't spin the loop.
            await asyncio.sleep(TICKLE_MIN_SLEEP)
            continue
