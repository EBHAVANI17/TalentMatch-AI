"""Fixed-window rate limiting.

Counts live in Redis when REDIS_URL is set (shared across API instances) and in
process memory otherwise (fine for local development and tests).

Limits are written like "10/minute", "300/minute", "5/second", "1000/hour".
"""
import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple, Union

from fastapi import HTTPException, Request, status

from app.core.config import settings

logger = logging.getLogger(__name__)

_PERIODS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}


@dataclass(frozen=True)
class Limit:
    count: int
    seconds: int

    @classmethod
    def parse(cls, text: str) -> "Limit":
        amount, _, period = text.strip().partition("/")
        return cls(count=int(amount), seconds=_PERIODS[period.strip().rstrip("s")])


class MemoryBackend:
    def __init__(self) -> None:
        self._windows: Dict[str, Tuple[int, int]] = {}
        self._lock = threading.Lock()

    def incr(self, key: str, window: int, seconds: int) -> int:
        with self._lock:
            start, count = self._windows.get(key, (window, 0))
            if start != window:
                start, count = window, 0
            count += 1
            self._windows[key] = (start, count)
            return count

    def reset(self) -> None:
        with self._lock:
            self._windows.clear()


class RedisBackend:
    def __init__(self, url: str) -> None:
        import redis

        self._redis = redis.Redis.from_url(url)

    def incr(self, key: str, window: int, seconds: int) -> int:
        redis_key = f"ratelimit:{key}:{window}"
        pipe = self._redis.pipeline()
        pipe.incr(redis_key)
        pipe.expire(redis_key, seconds + 1)
        return int(pipe.execute()[0])

    def reset(self) -> None:  # pragma: no cover - used only by tests with memory backend
        pass


def _make_backend():
    if settings.redis_url:
        try:
            backend = RedisBackend(settings.redis_url)
            backend._redis.ping()
            return backend
        except Exception as exc:  # Redis down shouldn't take the API down
            logger.warning("Rate limiter falling back to in-memory store: %s", exc)
    return MemoryBackend()


backend = _make_backend()


def hit(key: str, limit: Limit) -> Tuple[bool, int]:
    """Record one request. Returns (allowed, seconds until the window resets)."""
    now = int(time.time())
    window = now // limit.seconds
    try:
        count = backend.incr(key, window, limit.seconds)
    except Exception as exc:  # fail open on store errors
        logger.warning("Rate limiter store error: %s", exc)
        return True, 0
    retry_after = (window + 1) * limit.seconds - now
    return count <= limit.count, retry_after


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def rate_limit(scope: str, limit_text: Union[str, Callable[[], str]], key: Callable[[Request], str] = client_ip) -> Callable:
    """FastAPI dependency: Depends(rate_limit("auth", lambda: settings.rate_limit_auth)).

    Pass a callable to read the limit on every request (so config changes apply without a restart).
    """
    def current_limit() -> Limit:
        return Limit.parse(limit_text() if callable(limit_text) else limit_text)

    def dependency(request: Request) -> None:
        if not settings.rate_limit_enabled:
            return
        allowed, retry_after = hit(f"{scope}:{key(request)}", current_limit())
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again shortly.",
                headers={"Retry-After": str(retry_after)},
            )

    return dependency


def check_global_limit(request: Request) -> Optional[int]:
    """Used by middleware for the default per-IP API limit. Returns Retry-After when blocked."""
    if not settings.rate_limit_enabled:
        return None
    allowed, retry_after = hit(f"global:{client_ip(request)}", Limit.parse(settings.rate_limit_default))
    return None if allowed else retry_after
