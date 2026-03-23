"""
backend/mini_assistant/phase10/rate_limiter.py

Sliding-window rate limiter middleware.

Three tiers (applied in order, first failure wins):
  1. Per-IP general     : default 120 req / 60 s
  2. Per-IP heavy paths : default 20  req / 60 s  (AI endpoints)
  3. Per-user (JWT)     : plan-aware limits via safety module

Configuration via environment variables:
  RATE_LIMIT_IP_RPS       default 120
  RATE_LIMIT_IP_WINDOW    default 60   (seconds)
  RATE_LIMIT_HEAVY_RPS    default 20
  RATE_LIMIT_ENABLED      default 1    (set to 0 to disable)
"""
from __future__ import annotations

import logging
import os
import time
from collections import defaultdict, deque
from typing import Callable, Deque, Dict

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
def _int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except (ValueError, TypeError):
        return default

_ENABLED        = os.environ.get("RATE_LIMIT_ENABLED", "1").strip() != "0"
_IP_LIMIT       = _int("RATE_LIMIT_IP_RPS", 600)    # 600/60s = 10 req/s per IP
_IP_WINDOW      = _int("RATE_LIMIT_IP_WINDOW", 60)
_HEAVY_LIMIT    = _int("RATE_LIMIT_HEAVY_RPS", 120)  # 120/60s = 2 image gen/s per IP

# Paths that count as "heavy" (image gen + raw chat + app builder)
_HEAVY_PATHS = (
    "/image/generate",
    "/api/chat",
    "/image-api/api/chat",
    "/app-builder/generate",
    "/app-builder/export-zip",
    "/app-builder/github-push",
    "/app-builder/deploy-vercel",
)

# Paths that bypass rate limiting entirely
_EXEMPT_PREFIXES = (
    "/static/",
    "/Logo.png",
    "/favicon",
)


# ── Sliding window counter ────────────────────────────────────────────────────

class _SlidingWindow:
    """Thread-safe-ish deque-based sliding window counter."""

    def __init__(self, limit: int, window_s: int):
        self.limit    = limit
        self.window   = window_s
        self._buckets: Dict[str, Deque[float]] = defaultdict(deque)

    def is_allowed(self, key: str) -> bool:
        now  = time.monotonic()
        dq   = self._buckets[key]
        cutoff = now - self.window
        # Evict expired timestamps
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= self.limit:
            return False
        dq.append(now)
        return True

    def retry_after(self, key: str) -> int:
        """Seconds until the oldest request expires from the window."""
        dq = self._buckets.get(key)
        if not dq:
            return 0
        return max(0, int(self.window - (time.monotonic() - dq[0])) + 1)

    def stats(self, key: str) -> dict:
        dq = self._buckets.get(key, deque())
        return {"count": len(dq), "limit": self.limit, "window_s": self.window}


# ── Middleware ────────────────────────────────────────────────────────────────

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._ip_limiter    = _SlidingWindow(_IP_LIMIT,    _IP_WINDOW)
        self._heavy_limiter = _SlidingWindow(_HEAVY_LIMIT, _IP_WINDOW)
        if _ENABLED:
            logger.info(
                "RateLimitMiddleware: ENABLED — IP %d/%ds, heavy %d/%ds",
                _IP_LIMIT, _IP_WINDOW, _HEAVY_LIMIT, _IP_WINDOW,
            )
        else:
            logger.info("RateLimitMiddleware: DISABLED")

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not _ENABLED:
            return await call_next(request)

        path = request.url.path

        # Exempt paths
        if any(path.startswith(p) for p in _EXEMPT_PREFIXES):
            return await call_next(request)

        # Identify client: prefer JWT sub (per-user), fall back to forwarded IP
        # On Railway all traffic shares the same proxy IP, so IP-only bucketing
        # would rate-limit all users together. JWT gives true per-user isolation.
        client_key = None
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            try:
                import base64 as _b64, json as _j
                token = auth.split(" ", 1)[1]
                payload_b64 = token.split(".")[1]
                # Pad to multiple of 4
                payload_b64 += "=" * (4 - len(payload_b64) % 4)
                payload = _j.loads(_b64.urlsafe_b64decode(payload_b64))
                client_key = f"user:{payload.get('sub') or payload.get('email') or payload.get('uid')}"
            except Exception:
                pass

        ip = (
            request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            or request.headers.get("X-Real-IP", "")
            or (request.client.host if request.client else "unknown")
        )
        # Use JWT-based key for rate limiting when available
        rate_key = client_key or ip

        # General rate limit (per user or per IP)
        if not self._ip_limiter.is_allowed(rate_key):
            retry = self._ip_limiter.retry_after(rate_key)
            logger.warning("Rate limit (general): %s %s [%s]", rate_key, path, request.method)
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": str(retry)},
                content={
                    "detail": f"Too many requests. Retry after {retry}s.",
                    "retry_after": retry,
                },
            )

        # Heavy-endpoint sub-limit
        is_heavy = any(p in path for p in _HEAVY_PATHS)
        if is_heavy and not self._heavy_limiter.is_allowed(rate_key):
            retry = self._heavy_limiter.retry_after(rate_key)
            logger.warning("Rate limit (heavy): %s %s [%s]", rate_key, path, request.method)
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": str(retry)},
                content={
                    "detail": f"Image/chat rate limit exceeded. Retry after {retry}s.",
                    "retry_after": retry,
                },
            )

        response = await call_next(request)
        # Expose limit headers so the client can self-throttle
        stats = self._ip_limiter.stats(ip)
        remaining = max(0, stats["limit"] - stats["count"])
        response.headers["X-RateLimit-Limit"]     = str(stats["limit"])
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Window"]    = str(stats["window_s"])
        return response


def attach_rate_limiter(app) -> None:
    """Convenience: attach the middleware to a FastAPI app."""
    app.add_middleware(RateLimitMiddleware)
