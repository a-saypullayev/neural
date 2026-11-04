"""Small in-process sliding-window rate limiter (per server instance)."""
import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self):
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window: int):
        """Record a hit. Returns (allowed, remaining, retry_after_seconds)."""
        now = time.time()
        with self._lock:
            q = self._hits[key]
            while q and q[0] <= now - window:
                q.popleft()
            if len(q) >= limit:
                return False, 0, max(1, int(q[0] + window - now) + 1)
            q.append(now)
            if len(self._hits) > 20000:  # crude memory guard
                for k in [k for k, v in self._hits.items() if not v][:5000]:
                    self._hits.pop(k, None)
            return True, limit - len(q), 0


limiter = RateLimiter()
