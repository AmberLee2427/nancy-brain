"""Small in-process rate limiter for the hosted Nancy API."""

import math
import threading
import time
from collections import defaultdict, deque


class SlidingWindowRateLimiter:
    """Thread-safe sliding-window request counter."""

    def __init__(self, limit: int, window_seconds: int):
        self.limit = max(int(limit), 0)
        self.window_seconds = max(int(window_seconds), 1)
        self._events = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, identity: str) -> tuple[bool, int]:
        """Record a request and return (allowed, retry_after_seconds)."""
        if self.limit == 0:
            return True, 0

        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            events = self._events[identity]
            while events and events[0] <= cutoff:
                events.popleft()

            if len(events) >= self.limit:
                retry_after = max(1, math.ceil(events[0] + self.window_seconds - now))
                return False, retry_after

            events.append(now)
            return True, 0
