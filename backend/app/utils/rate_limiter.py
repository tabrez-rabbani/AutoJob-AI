"""
AutoJob AI — Rate Limiter Middleware
Lightweight in-memory rate limiting for FastAPI.
No external dependencies needed.

Limits:
  - General API: 60 requests/minute per IP
  - Auth endpoints: 10 requests/minute per IP (brute-force protection)
  - Automation endpoints: 5 requests/minute per IP (expensive operations)
"""

import time
import logging
from collections import defaultdict
from dataclasses import dataclass, field

from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger("autojob.rate_limiter")


@dataclass
class RateBucket:
    """Tracks request counts in a rolling time window."""
    requests: list[float] = field(default_factory=list)

    def add(self, now: float) -> None:
        self.requests.append(now)

    def count_in_window(self, now: float, window_seconds: int) -> int:
        """Count requests within the last `window_seconds`."""
        cutoff = now - window_seconds
        # Remove old entries (memory cleanup)
        self.requests = [t for t in self.requests if t > cutoff]
        return len(self.requests)


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """
    Per-IP rate limiting middleware.

    Applies different limits based on the endpoint path:
    - /api/auth/*          → 10 req/min (brute-force protection)
    - /api/automation/*    → 5 req/min  (expensive browser ops)
    - /api/*               → 60 req/min (general API)
    - Everything else      → no limit (health, docs, etc.)
    """

    # Rate limit rules: (path_prefix, max_requests, window_seconds)
    RULES = [
        ("/api/auth/", 10, 60),          # Auth: 10/min
        ("/api/automation/", 5, 60),     # Automation: 5/min
        ("/api/", 60, 60),               # General API: 60/min
    ]

    def __init__(self, app):
        super().__init__(app)
        # IP -> path_prefix -> RateBucket
        self._buckets: dict[str, dict[str, RateBucket]] = defaultdict(
            lambda: defaultdict(RateBucket)
        )
        self._last_cleanup = time.time()

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP, handling reverse proxies."""
        # Check X-Forwarded-For header (set by reverse proxies like Nginx)
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        # Check X-Real-IP (another common proxy header)
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
        # Direct connection
        return request.client.host if request.client else "unknown"

    def _cleanup_old_buckets(self, now: float) -> None:
        """Remove stale buckets every 5 minutes to prevent memory growth."""
        if now - self._last_cleanup < 300:  # 5 minutes
            return

        self._last_cleanup = now
        stale_ips = []
        for ip, prefixes in self._buckets.items():
            # Remove empty buckets
            empty_prefixes = [
                p for p, bucket in prefixes.items()
                if bucket.count_in_window(now, 300) == 0
            ]
            for p in empty_prefixes:
                del prefixes[p]
            if not prefixes:
                stale_ips.append(ip)

        for ip in stale_ips:
            del self._buckets[ip]

        if stale_ips:
            logger.debug(f"Rate limiter cleanup: removed {len(stale_ips)} stale IPs")

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        now = time.time()

        # Periodic cleanup
        self._cleanup_old_buckets(now)

        # Find the matching rate limit rule
        for prefix, max_requests, window in self.RULES:
            if path.startswith(prefix):
                client_ip = self._get_client_ip(request)
                bucket = self._buckets[client_ip][prefix]

                current_count = bucket.count_in_window(now, window)

                if current_count >= max_requests:
                    logger.warning(
                        f"Rate limit hit: {client_ip} on {prefix} "
                        f"({current_count}/{max_requests} in {window}s)"
                    )
                    return JSONResponse(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        content={
                            "detail": f"Too many requests. Limit: {max_requests} per {window}s. Please slow down.",
                        },
                        headers={"Retry-After": str(window)},
                    )

                bucket.add(now)
                break

        return await call_next(request)
