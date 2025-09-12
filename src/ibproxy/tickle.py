import asyncio
import logging
from datetime import datetime
from typing import Optional

import ibauth

from . import rate
from .const import DATETIME_FMT
from .status import get_system_status

# Seconds between tickling the IBKR API.
#
TICKLE_INTERVAL = 60
TICKLE_MIN_SLEEP = 5


async def tickle_loop(auth: Optional[ibauth.IBAuth], mode: Optional[str] = "always") -> None:
    """Periodically call auth.tickle() while the app is running."""
    if mode == "off":
        logging.warning("⛔ Tickle loop disabled.")
        return

    logging.info("⏰ Tickle loop starting (mode=%s)", mode)
    while True:
        sleep: float = TICKLE_INTERVAL
        try:
            status = await get_system_status()
            try:
                status = await asyncio.wait_for(get_system_status(), timeout=10.0)
            except asyncio.TimeoutError:
                logging.warning("🚧 IBKR status timed out!")
            else:
                logging.info("IBKR status: %s %s", status.colour, status.label)

            if auth is not None:
                if mode == "always":
                    auth.tickle()
                else:
                    if latest := rate.latest():
                        logging.info(" - Latest request: %s", datetime.fromtimestamp(latest).strftime(DATETIME_FMT))
                        delay = datetime.now().timestamp() - latest
                        if delay < TICKLE_INTERVAL:
                            logging.info("- Within tickle interval. No need to tickle again.")
                            sleep -= delay
                            sleep = max(sleep, TICKLE_MIN_SLEEP)
                        else:
                            auth.tickle()
                    else:
                        auth.tickle()
        except asyncio.CancelledError:
            # Allow friendly shutdown to cancel the task.
            logging.info("Tickle loop cancelled; exiting.")
            raise
        except Exception:
            # Log the exception and continue the loop after a short delay.
            logging.exception("Tickle failed. Will retry after short delay.")
            # Backoff a bit so repeated failures don't spin the loop.
            # TODO: Use tenacity to implement the retry with backoff.
            await asyncio.sleep(TICKLE_MIN_SLEEP)
            continue

        logging.debug("⏰ Sleep: %.1f s", sleep)
        await asyncio.sleep(sleep)
