"""
backend/mini_assistant/phase10/request_tracer.py

Request tracing middleware: attaches a unique X-Request-ID to every request
and logs method, path, status, and latency in a structured format.

Log format (JSON-compatible when using structlog, plain text otherwise):
  [TRACE] GET /api/chat  →  200  (142.3 ms)  req_id=abc123

Also exposes a module-level context var so any downstream code can call
  get_request_id()
to embed the trace ID in its own log lines.
"""
from __future__ import annotations

import logging
import time
import uuid
from contextvars import ContextVar
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("request_tracer")

# Context variable — readable anywhere in the same async task tree
_request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    """Return the current request's trace ID (empty string outside a request)."""
    return _request_id_var.get()


class RequestTracerMiddleware(BaseHTTPMiddleware):
    """
    Assigns a UUID request ID, stores it in a context var, injects it into
    response headers, and logs latency on completion.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate or forward a request ID
        req_id = (
            request.headers.get("X-Request-ID")
            or request.headers.get("x-request-id")
            or str(uuid.uuid4())[:12]
        )
        token = _request_id_var.set(req_id)

        t0 = time.perf_counter()
        try:
            response: Response = await call_next(request)
        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            logger.error(
                "[TRACE] %s %s → EXCEPTION (%.1f ms) req_id=%s  error=%s",
                request.method, request.url.path, elapsed, req_id, exc,
            )
            raise
        finally:
            _request_id_var.reset(token)

        elapsed = (time.perf_counter() - t0) * 1000
        status  = response.status_code

        log_fn = logger.warning if status >= 400 else logger.info
        log_fn(
            "[TRACE] %s %s → %d (%.1f ms) req_id=%s",
            request.method, request.url.path, status, elapsed, req_id,
        )

        # Inject trace headers into response
        response.headers["X-Request-ID"]    = req_id
        response.headers["X-Response-Time"] = f"{elapsed:.1f}ms"
        return response


def attach_tracer(app) -> None:
    """Convenience: attach the middleware to a FastAPI app."""
    app.add_middleware(RequestTracerMiddleware)
