"""
backend/mini_assistant/phase10/auth_middleware.py

API-key authentication middleware for FastAPI.

Behaviour:
  - If API_KEY env var is NOT set (or empty) → auth is disabled (dev mode).
  - If API_KEY is set → every request to a protected prefix must carry
    the matching key in the X-API-Key header (or ?api_key= query param).
  - Public paths (health checks, static files, frontend SPA) bypass auth.
  - Failed auth returns 401 JSON with a clear message.
"""
from __future__ import annotations

import logging
import os
from typing import Callable, List, Set

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# Paths that never require auth
_PUBLIC_PREFIXES: List[str] = [
    "/api/health",
    "/image-api/api/health",
    "/static/",
    "/Logo.png",
    "/favicon",
]

# Prefixes that ARE protected when API_KEY is configured
_PROTECTED_PREFIXES: List[str] = [
    "/api/",
    "/image-api/",
]


def _load_keys() -> Set[str]:
    """Load valid API keys from environment (comma-separated for multi-key support)."""
    raw = os.environ.get("API_KEY", "").strip()
    if not raw:
        return set()
    return {k.strip() for k in raw.split(",") if k.strip()}


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """
    Starlette/FastAPI middleware that enforces X-API-Key authentication.
    Attach to the FastAPI app once at startup.
    """

    def __init__(self, app, reload_keys: bool = False):
        super().__init__(app)
        self._keys = _load_keys()
        self._reload = reload_keys  # re-read env on every request (useful for secrets rotation)
        if self._keys:
            logger.info("ApiKeyMiddleware: auth ENABLED (%d key(s) configured)", len(self._keys))
        else:
            logger.info("ApiKeyMiddleware: auth DISABLED (API_KEY not set)")

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Re-load keys on every request if hot-reload is enabled
        if self._reload:
            self._keys = _load_keys()

        # Auth disabled → pass through
        if not self._keys:
            return await call_next(request)

        path = request.url.path

        # Public paths bypass auth
        if any(path.startswith(p) for p in _PUBLIC_PREFIXES):
            return await call_next(request)

        # Only enforce on protected prefixes
        if not any(path.startswith(p) for p in _PROTECTED_PREFIXES):
            return await call_next(request)

        # Extract key from header or query param
        provided = (
            request.headers.get("X-API-Key")
            or request.headers.get("x-api-key")
            or request.query_params.get("api_key")
        )

        if not provided or provided not in self._keys:
            logger.warning(
                "Auth rejected: %s %s — key=%s",
                request.method, path,
                f"{provided[:6]}…" if provided else "(none)",
            )
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized — valid X-API-Key required."},
            )

        return await call_next(request)


def attach_auth(app) -> None:
    """Convenience: attach the middleware to a FastAPI app."""
    app.add_middleware(ApiKeyMiddleware)
