import asyncio
import logging
from datetime import datetime
from enum import Enum

import httpx
import ibauth

from . import rate
from .const import DATETIME_FMT
from .system.status import get_system_status

# Seconds between tickling the IBKR API.
#
TICKLE_INTERVAL: float = 120
TICKLE_MIN_SLEEP: float = 5


class TickleMode(str, Enum):
    ALWAYS = "always"  # Default
    AUTO = "auto"
    OFF = "off"


async def log_status() -> None:
    try:
        status = await asyncio.wait_for(get_system_status(), timeout=10.0)
    except (asyncio.TimeoutError, httpx.ConnectTimeout):
        logging.warning("🚧 Status request timed out!")
    except RuntimeError as error:
        logging.error(error)
    else:
        logging.info("Status: %s %s", status.colour, status.label)


async def tickle_loop(
    auth: ibauth.IBAuth, mode: TickleMode = TickleMode.ALWAYS, interval: float = TICKLE_INTERVAL
) -> None:
    """
    Periodically call auth.tickle() while the app is running.
    """
    if mode == TickleMode.OFF:
        logging.warning("⛔ Tickle loop disabled.")
        return

    async def should_tickle() -> tuple[bool, float]:
        if mode == TickleMode.ALWAYS:
            return True, interval
        else:
            if latest := rate.latest():
                logging.info(" - Latest request: %s", datetime.fromtimestamp(latest).strftime(DATETIME_FMT))
                delay = datetime.now().timestamp() - latest
                if delay < interval:
                    logging.info("- Within tickle interval. No need to tickle again.")
                    return False, max(interval - delay, TICKLE_MIN_SLEEP)

        return True, interval

    logging.info("🔁 Start tickle loop (mode='%s', interval=%.1f s).", mode, interval)
    delay: float = 0
    while True:
        logging.debug("⏳ Sleep: %.1f s", delay)
        await asyncio.sleep(delay)

        await rate.log()

        try:
            await log_status()

            should, delay = await should_tickle()
            if should:
                await auth.tickle()

            if not auth.is_connected():
                logging.warning("🚨 Not connected.")
                # TODO: Replicate manual restart.
        except Exception:
            logging.error("🚨 Tickle failed.")
            # Backoff a bit so repeated failures don't spin the loop.
            await asyncio.sleep(TICKLE_MIN_SLEEP)
            continue
