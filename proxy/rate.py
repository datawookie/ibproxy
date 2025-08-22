import time
from collections import defaultdict, deque
from datetime import UTC, datetime
from threading import Lock

times: dict[str, deque[float]] = defaultdict(deque)

lock = Lock()

# Sliding window in seconds.
#
# This is the time interval that's used to calculate the rates.
#
WINDOW = 5

# IBKR rate limits are documented at https://www.interactivebrokers.com/campus/ibkr-api-page/web-api-trading/#pacing-limitations-8.


def record(endpoint: str) -> datetime:
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
        # Prune old entries.
        while dq and dq[0] < now - WINDOW:
            dq.popleft()

    return datetime.fromtimestamp(now, tz=UTC)


def rate(endpoint: str | None = None) -> tuple[float | None, float | None]:
    """
    Compute sliding-window average requests per second.

    It also returns the inverse of this frequency. This is similar to (but not
    the same as) the average period between requests. Calculating that correctly
    would require a bit more work and since this is possibly being done
    frequently it's probably not worth the extra time.

    Args:
        endpoint (str | None): The API endpoint to compute the rate for. If None, computes the overall rate.
    """
    with lock:
        if endpoint is None:
            # Consolidate times over all paths.
            dq = [t for dq in times.values() for t in dq]
            # Sort because they are not out of order.
            dq.sort()
        else:
            dq = times[endpoint]  # type: ignore[assignment]

        n = len(dq)

        if not dq or n < 2:
            elapsed = 0.0
        else:
            elapsed = dq[-1] - dq[0]

        rate = n / elapsed if elapsed > 0 else None
        period = 1 / rate if rate is not None else None

        return rate, period


def format(rate: float | None) -> str:
    """
    Format a rate value for logging.

    Args:
        rate (float | None): The rate to format.
    """
    return f"{rate:5.2f}" if rate is not None else "-----"
