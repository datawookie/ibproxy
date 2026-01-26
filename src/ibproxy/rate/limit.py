import asyncio
import logging
import time
from threading import RLock

from ..const import RATE_LIMIT, RATE_LIMIT_BURST


class LeakyBucket:
    """
    Leaky bucket rate limiter implementation.

    Uses a token-bucket algorithm where tokens are generated at a fixed rate.
    Each request consumes one token. If no tokens are available, the the request is rate-limited.
    Supports burst capacity to allow temporary spikes above the sustained rate.
    """

    def __init__(self, rate: float, burst: float):
        """
        Initialize the leaky bucket.

        Args:
            rate: Refill rate (requests per second)
            burst: Maximum tokens available (burst capacity)
        """
        self.rate = rate
        self.burst = burst
        self.tokens = burst
        self.last_refill = time.time()
        self.lock = RLock()

    async def acquire(self, tokens: float = 1.0) -> tuple[bool, float]:
        """
        Attempt to acquire tokens from the bucket.

        Args:
            tokens: Number of tokens to acquire (default: 1.0)

        Returns:
            Tuple of (acquired, wait_time) where:
            - acquired: True if tokens were available, False if rate-limited;
            - wait_time: Seconds to wait before retry if rate-limited, else 0.
        """
        with self.lock:
            now = time.time()

            # Calculate tokens generated since last refill.
            elapsed = now - self.last_refill
            refill = elapsed * self.rate

            # Add generated tokens (capped at burst).
            self.tokens = min(self.burst, self.tokens + refill)
            self.last_refill = now

            if self.tokens >= tokens:
                self.tokens -= tokens
                logging.debug(f"⏳ Rate limit: acquired {tokens}, {self.tokens:.2f} remaining.")
                return True, 0.0
            else:
                tokens_needed = tokens - self.tokens
                wait_time = tokens_needed / self.rate
                logging.debug(f"⏳ Rate limit: insufficient tokens (wait {wait_time:.3f} s).")
                return False, wait_time


# Global leaky bucket instance
_bucket = LeakyBucket(RATE_LIMIT, RATE_LIMIT_BURST)


async def enforce_rate_limit() -> None:
    """
    Enforce the global rate limit using the leaky bucket algorithm.

    This function blocks until a token is available, implementing backpressure
    for requests that exceed the sustained rate limit.

    Raises:
        No exceptions, but will sleep as needed to enforce the rate limit.
    """
    acquired, wait_time = await _bucket.acquire(tokens=1.0)

    if not acquired:
        logging.warning(f"⏳ Rate limit exceeded (wait {wait_time:.3f} s).")
        await asyncio.sleep(wait_time)
        # Recursively call to acquire after waiting.
        await enforce_rate_limit()
