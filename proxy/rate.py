import time
from collections import defaultdict, deque
from datetime import UTC, datetime
from threading import Lock

times: dict[str, deque[float]] = defaultdict(deque)

lock = Lock()

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


def rate(endpoint: str | None = None) -> float:
    """
    Compute sliding-window average requests per second.

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
            dq = times.get(endpoint)  # type: ignore[assignment]

        n = len(dq)

        if not dq or n < 2:
            return 0.0

        elapsed = dq[-1] - dq[0]

        return n / elapsed if elapsed > 0 else 0.0
