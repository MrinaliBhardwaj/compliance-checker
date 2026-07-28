"""
Fixed-window rate limiter for the auth endpoints (brute-force / credential-stuffing
guard on login and invite acceptance).

Backend: Redis when REGIS_REDIS_URL is reachable — shared across every uvicorn
worker and replica, which is the only correct choice in production (an in-process
counter would give an attacker a fresh budget per worker). Falls back to an
in-process counter for local/dev/tests (no Redis needed).

Fails OPEN on backend errors: we throttle attackers, we don't lock real users out
because Redis hiccuped. The per-account limit still holds the line when the
per-IP layer is defeated (e.g. a spoofed X-Forwarded-For behind a bad proxy).
"""
from __future__ import annotations

import threading
import time

from fastapi import Request

from app.core.config import get_settings


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after


class _MemoryBackend:
    """Per-process fixed-window counter (dev/tests only)."""

    def __init__(self) -> None:
        self._hits: dict[str, tuple[int, float]] = {}  # key -> (count, window_start)
        self._lock = threading.Lock()

    def incr(self, key: str, window: int) -> int:
        now = time.time()
        with self._lock:
            count, start = self._hits.get(key, (0, now))
            if now - start >= window:
                count, start = 0, now
            count += 1
            self._hits[key] = (count, start)
            return count

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()


class _RedisBackend:
    """Shared fixed-window counter across workers/replicas (production)."""

    def __init__(self, client) -> None:
        self._r = client

    def incr(self, key: str, window: int) -> int:
        count = int(self._r.incr(key))
        if count == 1:  # first hit in this window -> start the TTL
            self._r.expire(key, window)
        return count

    def reset(self, key: str) -> None:
        self._r.delete(key)

    def clear(self) -> None:  # prod never calls this; tests use memory
        pass


_backend = None


def _get_backend():
    global _backend
    if _backend is not None:
        return _backend
    try:
        import redis  # sync client; declared dep (arq also uses redis)
        client = redis.Redis.from_url(
            get_settings().redis_url, socket_connect_timeout=0.25,
            socket_timeout=0.25, decode_responses=True)
        client.ping()
        _backend = _RedisBackend(client)
    except Exception:
        _backend = _MemoryBackend()  # no Redis -> per-process fallback
    return _backend


def client_ip(request: Request) -> str:
    """Best-effort client IP. In production this must sit behind a proxy/LB that
    sets a trustworthy X-Forwarded-For (Vercel/Railway/ALB do). A spoofed XFF only
    defeats the per-IP layer — the per-account limit is unaffected."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def hit(scope: str, identifier: str, *, limit: int, window: int) -> None:
    """Count one attempt against (scope, identifier); raise RateLimitExceeded once
    the window budget is spent. Backend errors fail open (no raise)."""
    key = f"rl:{scope}:{identifier.lower()}"
    try:
        count = _get_backend().incr(key, window)
    except Exception:
        return
    if count > limit:
        raise RateLimitExceeded(retry_after=window)


def reset(scope: str, identifier: str) -> None:
    """Clear the counter (called on a successful auth so honest users are never
    throttled for a few earlier typos)."""
    try:
        _get_backend().reset(f"rl:{scope}:{identifier.lower()}")
    except Exception:
        pass


def clear() -> None:
    """Test hook: wipe the in-process counter between tests."""
    try:
        _get_backend().clear()
    except Exception:
        pass
