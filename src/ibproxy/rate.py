import asyncio
import logging
import time
from collections import defaultdict, deque
from datetime import UTC, datetime
from threading import RLock

from .const import RATE_LOG_INTERVAL

times: dict[str, deque[float]] = defaultdict(deque)

# Use a re-entrant lock to allow functions that have acquired the lock to call
# other functions that also acquire the lock.
#
lock = RLock()

# Sliding window in seconds.
#
# This is the time interval that's used to calculate the rates.
#
WINDOW = 30

# IBKR rate limits are documented at
#
# https://www.interactivebrokers.com/campus/ibkr-api-page/web-api-trading/#pacing-limitations-8.
#
# There's a global limit of 50 requests per second. However, there are specific
# limits applied to some endpoints that are more restrictive.

# TODO: Could we use https://github.com/ZhuoZhuoCrayon/throttled-py?


async def prune(queue: deque[float] | None = None, now: float | None = None) -> None:
    """
    Prune old timestamps from the deques.

    Args:
        dq (deque[float] | None): The deque to prune. If None, prunes all deques.
    """
    if now is None:
        now = time.time()

    with lock:
        for dq in [queue] if queue else times.values():
            while dq and dq[0] < now - WINDOW:
                logging.debug("Prune timestamp (%.3f).", dq[0])
                dq.popleft()


async def record(endpoint: str) -> datetime:
    """
    Record the current request timestamp.

    Args:
        endpoint (str | None): The API endpoint called.
    """
    now = time.time()

    with lock:
        # Add the current time to the deque.
        dq = times[endpoint]
        dq.append(now)

    await prune(dq, now)

    return datetime.fromtimestamp(now, tz=UTC)


def latest(endpoint: str | None = None) -> float | None:
    """
    Get the latest request timestamp.

    Args:
        endpoint (str | None): The API endpoint to get the latest timestamp for. If None, gets the overall latest timestamp.
    """
    with lock:
        if endpoint is None:
            # Consolidate times over all paths.
            return max((dq[-1] for dq in times.values() if dq), default=None)
        else:
            dq = times[endpoint]
            return dq[-1] if dq else None


async def rate(endpoint: str | None = None) -> tuple[float | None, float | None]:
    """
    Compute sliding-window average requests per second.

    It also returns the inverse of this frequency. This is similar to (but not
    the same as) the average period between requests. Calculating that correctly
    would require a bit more work and since this is possibly being done
    frequently it's probably not worth the extra time.

    🚨 This function does not prune the times to the window duration. This is
    only done when new times are added to the queue. So it's possible to get
    averages times that are longer than the window duration.

    Args:
        endpoint (str | None): The API endpoint to compute the rate for. If None, computes the overall rate.
    """
    with lock:
        if endpoint is None:
            # Prune all queues because there might be old timestamps in some.
            #
            # This is necessary because we are consolidating times over all
            # paths and some of them might not have been called (and hence
            # pruned recently).
            #
            await prune()
            #
            # Consolidate times over all paths.
            dq = [t for sublist in times.values() for t in sublist]
            dq.sort()
        else:
            dq = times[endpoint]  # type: ignore[assignment]

        logging.debug("Timestamps: %s", list(dq))

        n = len(dq)

        if not dq or n < 2:
            # Not enough data to compute a rate.
            elapsed = 0.0
        else:
            # Time difference between the first and last timestamps.
            elapsed = dq[-1] - dq[0]

        # Number of requests per second.
        rate = n / elapsed if elapsed > 0 else None
        # Average period between requests (approximation).
        period = 1 / rate if rate is not None else None

        return rate, period


def format(rate: float | None) -> str:
    """
    Format a rate value for logging.

    Args:
        rate (float | None): The rate to format.
    """
    return f"{rate:5.2f}" if rate is not None else "-----"


async def log(endpoint: str | None = None) -> None:
    rps, period = await rate(endpoint)
    logging.info(f"⌚ Request rate (last {WINDOW} s): {format(rps)} Hz / {format(period)} s | ({endpoint or 'global'})")


async def rate_loop() -> None:
    while True:
        await asyncio.sleep(RATE_LOG_INTERVAL)
        await log()
