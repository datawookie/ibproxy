import asyncio
import logging
from datetime import datetime
from enum import Enum

import httpx

from . import rate
from .const import DATETIME_FMT
from .system.status import get_system_status
from .util import cpu_percent, disk_percent, ram_percent, swap_percent

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


async def tickle_loop(app: object) -> None:
    """
    Periodically call auth.tickle() while the app is running.

    The auth object and tickle parameters are fetched from app.state on each
    iteration, allowing the loop to use current values even if they're updated.
    """

    async def should_tickle() -> tuple[bool, float]:
        mode = app.state.args.tickle_mode  # type: ignore[attr-defined]
        interval = app.state.args.tickle_interval  # type: ignore[attr-defined]
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

    delay: float = 0
    while True:
        mode = app.state.args.tickle_mode  # type: ignore[attr-defined]

        if mode == TickleMode.OFF:
            logging.warning("⛔ Tickle loop disabled.")
            return

        logging.debug("⏳ Sleep: %.1f s", delay)
        await asyncio.sleep(delay)

        await rate.log()

        try:
            auth = app.state.auth  # type: ignore[attr-defined]
            logging.debug(f"🆔 Authentication object ID: {id(auth)}")
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

        try:
            cpu, ram, swap, disk = await asyncio.gather(
                cpu_percent(),
                ram_percent(),
                swap_percent(),
                disk_percent(),
            )
            logging.info(f"- CPU: {cpu:5.1f}% | RAM: {ram:5.1f}% | Swap: {swap:5.1f}% | Disk: {disk:5.1f}%")
        except Exception:
            logging.error("🚨 Failed to collect system metrics.")
