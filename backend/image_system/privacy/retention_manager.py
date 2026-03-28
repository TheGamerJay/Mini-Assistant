"""
Retention Manager — TTL-based cleanup for Tier C data stores.

Tier C records have a maximum retention of 30 days.  This module provides:
  • `purge_expired(store_path, ttl_days)`  — delete records older than TTL
  • `schedule_background_purge()`          — fire-and-forget asyncio task
  • `get_store_stats(store_path)`          — count live vs expired records

Supported store format: JSON file containing a list of dicts, each with an
"recorded_at" ISO-8601 timestamp field.  Compatible with the format used by
learning_engine.py and task_data_pipeline.py.

The purge job runs automatically once per server start (non-blocking) and can
be triggered manually via the /api/privacy/purge endpoint.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_TTL_DAYS = 30

# Stores subject to Tier C TTL enforcement
_TIER_C_STORES: List[str] = [
    "memory_store/tier_c_records.json",
    "memory_store/task_analytics.json",
]


# ---------------------------------------------------------------------------
# Core purge logic
# ---------------------------------------------------------------------------

def purge_expired(
    store_path: str | Path,
    ttl_days: int = DEFAULT_TTL_DAYS,
) -> Tuple[int, int]:
    """
    Remove records older than `ttl_days` from a JSON list store.

    Args:
        store_path: Path to the JSON file (list of dicts with "recorded_at").
        ttl_days:   Maximum age of records to keep.

    Returns:
        (kept, deleted) counts.
    """
    path = Path(store_path)
    if not path.exists():
        return 0, 0

    try:
        with open(path, "r", encoding="utf-8") as f:
            records: List[Dict[str, Any]] = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("retention_manager: failed to read %s — %s", path, exc)
        return 0, 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=ttl_days)

    kept: List[Dict[str, Any]] = []
    deleted = 0

    for rec in records:
        ts_raw = rec.get("recorded_at") or rec.get("timestamp") or ""
        try:
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts >= cutoff:
                kept.append(rec)
            else:
                deleted += 1
        except (ValueError, AttributeError):
            kept.append(rec)   # keep records with unparseable timestamps

    if deleted:
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(kept, f, indent=2)
            logger.info(
                "retention_manager: purged %d expired records from %s (%d kept)",
                deleted, path.name, len(kept),
            )
        except OSError as exc:
            logger.error("retention_manager: failed to write %s — %s", path, exc)

    return len(kept), deleted


def purge_all_tier_c(base_dir: Optional[str] = None) -> Dict[str, Dict[str, int]]:
    """
    Purge all known Tier C stores.

    Args:
        base_dir: Root directory containing memory_store/.
                  Defaults to the backend root derived from this file's location.

    Returns:
        Dict mapping store name → {"kept": N, "deleted": N}
    """
    if base_dir is None:
        # Resolve relative to this file:  .../image_system/privacy/ → ../../../
        base_dir = str(Path(__file__).resolve().parent.parent.parent.parent)

    results: Dict[str, Dict[str, int]] = {}
    for rel_path in _TIER_C_STORES:
        full = Path(base_dir) / rel_path
        kept, deleted = purge_expired(full)
        results[rel_path] = {"kept": kept, "deleted": deleted}

    return results


def get_store_stats(
    store_path: str | Path,
    ttl_days: int = DEFAULT_TTL_DAYS,
) -> Dict[str, int]:
    """
    Return counts of live vs expired records without deleting anything.

    Returns:
        {"total": N, "live": N, "expired": N}
    """
    path = Path(store_path)
    if not path.exists():
        return {"total": 0, "live": 0, "expired": 0}

    try:
        with open(path, "r", encoding="utf-8") as f:
            records: List[Dict[str, Any]] = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"total": 0, "live": 0, "expired": 0}

    cutoff = datetime.now(timezone.utc) - timedelta(days=ttl_days)
    live = expired = 0

    for rec in records:
        ts_raw = rec.get("recorded_at") or rec.get("timestamp") or ""
        try:
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts >= cutoff:
                live += 1
            else:
                expired += 1
        except (ValueError, AttributeError):
            live += 1

    return {"total": len(records), "live": live, "expired": expired}


# ---------------------------------------------------------------------------
# Background scheduler
# ---------------------------------------------------------------------------

async def _background_purge() -> None:
    """Run purge_all_tier_c in a thread pool so it doesn't block the event loop."""
    try:
        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(None, purge_all_tier_c)
        total_deleted = sum(v["deleted"] for v in results.values())
        if total_deleted:
            logger.info("retention_manager: background purge removed %d records total", total_deleted)
    except Exception as exc:
        logger.warning("retention_manager: background purge failed — %s", exc)


def schedule_background_purge() -> None:
    """
    Schedule a one-shot background purge task.

    Safe to call at server startup — runs without blocking the main thread.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(_background_purge())
        else:
            logger.debug("retention_manager: no running event loop — skipping background purge")
    except RuntimeError:
        pass   # no event loop at all (e.g. during tests)
