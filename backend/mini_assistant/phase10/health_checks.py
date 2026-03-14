"""
backend/mini_assistant/phase10/health_checks.py

Deep health-check module — probes every major dependency and returns a
structured report used by GET /api/health (upgraded) and the monitoring layer.

Dependencies checked:
  - Ollama (HTTP GET /api/tags)
  - ComfyUI (HTTP GET /)
  - Redis (PING)
  - MongoDB (server_info)
  - Phase modules (import availability)
  - Disk space (memory_store directory)
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

_OLLAMA_URL  = os.environ.get("OLLAMA_URL") or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
_COMFY_URL   = os.environ.get("COMFYUI_URL", "http://localhost:8188")
_TIMEOUT     = 5.0   # seconds per probe


# ---------------------------------------------------------------------------
# Individual probes
# ---------------------------------------------------------------------------

async def _probe_http(name: str, url: str, timeout: float = _TIMEOUT) -> dict:
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(url)
        ms = (time.perf_counter() - t0) * 1000
        return {"name": name, "status": "ok", "latency_ms": round(ms, 1), "http_status": r.status_code}
    except Exception as exc:
        ms = (time.perf_counter() - t0) * 1000
        return {"name": name, "status": "error", "latency_ms": round(ms, 1), "error": str(exc)[:120]}


async def _probe_redis() -> dict:
    t0 = time.perf_counter()
    try:
        import redis.asyncio as aioredis
        url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        r = aioredis.from_url(url, socket_connect_timeout=3)
        pong = await r.ping()
        await r.aclose()
        ms = (time.perf_counter() - t0) * 1000
        return {"name": "redis", "status": "ok" if pong else "degraded", "latency_ms": round(ms, 1)}
    except ImportError:
        return {"name": "redis", "status": "unavailable", "error": "redis package not installed"}
    except Exception as exc:
        ms = (time.perf_counter() - t0) * 1000
        return {"name": "redis", "status": "error", "latency_ms": round(ms, 1), "error": str(exc)[:120]}


async def _probe_mongo() -> dict:
    t0 = time.perf_counter()
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
        uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
        client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=3000)
        info = await client.server_info()
        await client.close()
        ms = (time.perf_counter() - t0) * 1000
        return {
            "name": "mongodb",
            "status": "ok",
            "latency_ms": round(ms, 1),
            "version": info.get("version", "?"),
        }
    except ImportError:
        return {"name": "mongodb", "status": "unavailable", "error": "motor package not installed"}
    except Exception as exc:
        ms = (time.perf_counter() - t0) * 1000
        return {"name": "mongodb", "status": "error", "latency_ms": round(ms, 1), "error": str(exc)[:120]}


def _probe_disk() -> dict:
    """Check available disk space in the memory_store directory."""
    try:
        import shutil
        store = Path(__file__).parent.parent.parent / "memory_store"
        store.mkdir(parents=True, exist_ok=True)
        total, used, free = shutil.disk_usage(str(store))
        free_mb  = free  // (1024 * 1024)
        total_mb = total // (1024 * 1024)
        status = "ok" if free_mb > 100 else ("warn" if free_mb > 20 else "critical")
        return {
            "name": "disk",
            "status": status,
            "free_mb": free_mb,
            "total_mb": total_mb,
            "used_pct": round(used / total * 100, 1),
        }
    except Exception as exc:
        return {"name": "disk", "status": "error", "error": str(exc)[:120]}


def _probe_phases() -> dict:
    """Check that all Phase modules are importable."""
    phases = {
        "phase1": "mini_assistant.phase1.planner",
        "phase2": "mini_assistant.phase2.ceo",
        "phase3": "mini_assistant.phase3.skill_registry",
        "phase4": "mini_assistant.phase4.mission_manager",
        "phase6": "mini_assistant.phase6.session_memory",
        "phase8": "mini_assistant.phase8.tool_registry",
        "phase9": "mini_assistant.phase9.learning_brain",
        "phase10": "mini_assistant.phase10.auth_middleware",
    }
    results = {}
    for label, module in phases.items():
        try:
            __import__(module)
            results[label] = "ok"
        except Exception as exc:
            results[label] = f"error: {exc}"
    return {"name": "phases", "status": "ok" if all(v == "ok" for v in results.values()) else "degraded", "details": results}


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------

async def run_health_checks(include_slow: bool = False) -> Dict[str, Any]:
    """
    Run all probes concurrently and return a structured report.

    include_slow: if False, skip MongoDB (often slow on cold start).
    """
    t0 = time.perf_counter()

    probes = [
        _probe_http("ollama",  f"{_OLLAMA_URL}/api/tags"),
        _probe_http("comfyui", f"{_COMFY_URL}/"),
        _probe_redis(),
    ]
    if include_slow:
        probes.append(_probe_mongo())

    results: List[dict] = await asyncio.gather(*probes, return_exceptions=True)

    # Unwrap any exceptions from gather
    checks = []
    for r in results:
        if isinstance(r, Exception):
            checks.append({"name": "unknown", "status": "error", "error": str(r)})
        else:
            checks.append(r)

    # Synchronous probes
    checks.append(_probe_disk())
    checks.append(_probe_phases())

    total_ms = (time.perf_counter() - t0) * 1000
    overall  = "ok"
    for c in checks:
        s = c.get("status", "ok")
        if s in ("error", "critical"):
            overall = "degraded"
            break
        elif s in ("warn", "degraded") and overall == "ok":
            overall = "warn"

    return {
        "status":    overall,
        "checks":    checks,
        "total_ms":  round(total_ms, 1),
    }
