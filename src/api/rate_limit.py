from __future__ import annotations

import time
from collections.abc import Callable

_MAX_KEYS = 10_000


class TokenBucketLimiter:
    """In-process token bucket (OWASP: rate limiting and abuse controls).
    Each key gets `per_minute` requests of burst that refill continuously.
    State lives in this process, so it does not hold across several
    instances; that gap is recorded in docs/SYSTEM-DESIGN.md."""

    def __init__(self, per_minute: int, clock: Callable[[], float] = time.monotonic) -> None:
        self._capacity = float(per_minute)
        self._refill_per_second = per_minute / 60.0
        self._clock = clock
        self._buckets: dict[str, tuple[float, float]] = {}

    def allow(self, key: str) -> bool:
        now = self._clock()
        tokens, last = self._buckets.get(key, (self._capacity, now))
        tokens = min(self._capacity, tokens + (now - last) * self._refill_per_second)
        allowed = tokens >= 1.0
        self._buckets[key] = (tokens - 1.0 if allowed else tokens, now)
        if len(self._buckets) > _MAX_KEYS:
            oldest = sorted(self._buckets.items(), key=lambda kv: kv[1][1])[: _MAX_KEYS // 10]
            for stale_key, _ in oldest:
                del self._buckets[stale_key]
        return allowed

    def retry_after_seconds(self) -> int:
        return max(1, int(1.0 / self._refill_per_second)) if self._refill_per_second else 60
