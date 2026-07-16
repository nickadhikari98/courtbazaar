"""Sliding-window rate limiter, isolated behind a small interface so the
in-process implementation can be swapped for a Redis-backed one later
without touching any call site.

Call sites only ever do:

    from rate_limiter import get_limiter
    get_limiter("lead_draft_create", limit=8, window_seconds=3600).check(key)

`get_limiter` returns whatever backend is configured (in-process today).
To move to Redis in a multi-worker/multi-instance deployment, add a
RedisSlidingWindowLimiter here implementing the same `.check(key)` contract
and switch what `get_limiter` constructs — no business logic elsewhere
changes.
"""
import time
from typing import Dict, List

from fastapi import HTTPException


class InProcessSlidingWindowLimiter:
    """Good enough for a single-worker deployment. Not shared across worker
    processes or instances — a multi-worker/multi-instance deployment needs
    the Redis-backed equivalent instead (see module docstring)."""

    def __init__(self, limit: int, window_seconds: int, message: str):
        self.limit = limit
        self.window_seconds = window_seconds
        self.message = message
        self._log: Dict[str, List[float]] = {}

    def check(self, key: str) -> None:
        now = time.time()
        recent = [t for t in self._log.get(key, []) if now - t < self.window_seconds]
        if len(recent) >= self.limit:
            raise HTTPException(429, self.message)
        recent.append(now)
        self._log[key] = recent


_limiters: Dict[str, InProcessSlidingWindowLimiter] = {}


def get_limiter(name: str, limit: int, window_seconds: int, message: str = "Too many requests. Please try again later.") -> InProcessSlidingWindowLimiter:
    """Returns a process-wide singleton limiter for `name`, creating it on
    first use. `limit`/`window_seconds`/`message` only take effect the first
    time a given `name` is requested."""
    if name not in _limiters:
        _limiters[name] = InProcessSlidingWindowLimiter(limit, window_seconds, message)
    return _limiters[name]
