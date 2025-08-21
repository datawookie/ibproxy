import time
from collections import deque
from threading import Lock

request_times: deque[float] = deque()

lock = Lock()

WINDOW = 5


def record() -> None:
    """
    Record the current request timestamp.
    """
    now = time.time()

    with lock:
        # Add the current time to the deque.
        request_times.append(now)
        # Prune old entries.
        while request_times and request_times[0] < now - WINDOW:
            request_times.popleft()


def rate() -> float:
    """
    Compute sliding-window average requests per second.
    """
    with lock:
        n = len(request_times)
        if n < 2:
            return 0.0
        elapsed = request_times[-1] - request_times[0]
    return n / elapsed if elapsed > 0 else 0.0
