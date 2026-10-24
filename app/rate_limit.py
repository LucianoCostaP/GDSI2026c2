import math
import threading
import time
from collections import deque
from collections.abc import Callable

from fastapi import HTTPException, Request, status

from .config import settings


class RateLimiter:
    """Ventana deslizante en memoria: como mucho `limit` intentos por clave cada `window` segundos.

    Vive en el proceso, así que con varias instancias del back cada una cuenta por su lado.
    """

    def __init__(
        self,
        limit: int,
        window: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limit = limit
        self.window = window
        self.clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str) -> float | None:
        """Registra un intento. Devuelve cuántos segundos esperar si se pasó del límite."""
        now = self.clock()
        with self._lock:
            self._forget_older_than(now - self.window)
            hits = self._hits.setdefault(key, deque())
            if len(hits) >= self.limit:
                return hits[0] + self.window - now
            hits.append(now)
            return None

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def _forget_older_than(self, cutoff: float) -> None:
        for key in list(self._hits):
            hits = self._hits[key]
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if not hits:
                del self._hits[key]


def limit_by_ip(limiter: RateLimiter) -> Callable[[Request], None]:
    def dependency(request: Request) -> None:
        ip = request.client.host if request.client else "unknown"
        check_key(limiter, ip)

    return dependency


def check_key(limiter: RateLimiter, key: str) -> None:
    retry_after = limiter.hit(key)
    if retry_after is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "TOO_MANY_ATTEMPTS",
            headers={"Retry-After": str(math.ceil(retry_after))},
        )


# Pedidos de código (activación y login de las dos puertas), cross-cutting sección 3.
ip_limiter = RateLimiter(settings.ip_rate_limit, settings.ip_rate_window_seconds)
identifier_limiter = RateLimiter(
    settings.identifier_rate_limit, settings.identifier_rate_window_seconds
)
