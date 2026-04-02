"""
billing/rate_limiter.py — Per-user rate limiting + abuse detection.

Protects against:
  - Rapid repeated requests (spam)
  - Burst abuse (many requests in a short window)
  - Abnormal usage patterns (automated probing)

Strategy:
  - Sliding window counters stored in memory (per process)
  - Two windows: per-minute (tight) and per-hour (burst budget)
  - For multi-process deployments, use Redis (see upgrade path below)

Limits (conservative defaults):
  free tier:    10 req/min,  60 req/hour
  paid tier:    30 req/min, 200 req/hour
  admin:        unlimited

Response:
  - throttle (429) with retry_after_seconds — NOT a full block
  - extreme abuse (>5x normal rate) → cooldown (60s)

CEO calls check_rate_limit() BEFORE probe detection.
Never raises — always returns a result dict.

────────────────────────────────────────────────────────────────────────────
SCALING NOTE — SINGLE-PROCESS LIMITATION
────────────────────────────────────────────────────────────────────────────

Current implementation is per-process in-memory. This means:

  - Works correctly for single-instance deployments (Railway hobby, single dyno)
  - Under horizontal scale (N instances), effective rate limit is N × configured_limit
    because each instance maintains its own independent counter
  - Process restart clears all counters — a burst could slip through at restart

This is ACCEPTABLE for current scale. Do NOT implement Redis prematurely.

UPGRADE PATH (when horizontal scale requires it):
────────────────────────────────────────────────────────────────────────────

Replace the in-memory deques with Redis sorted sets using the same sliding
window logic. Requires: redis-py, REDIS_URL env var.

  import redis
  _redis = redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)

  def check_rate_limit(user_id, user_tier="free"):
      tier   = (user_tier or "free").lower()
      limits = _LIMITS.get(tier, _LIMITS["free"])
      now    = time.time()

      key_min  = f"rl:min:{user_id}"
      key_hour = f"rl:hr:{user_id}"

      pipe = _redis.pipeline()
      # Atomic sliding window via sorted set + score = timestamp
      cutoff_min  = now - _WINDOW_MINUTE
      cutoff_hour = now - _WINDOW_HOUR

      pipe.zremrangebyscore(key_min,  "-inf", cutoff_min)
      pipe.zremrangebyscore(key_hour, "-inf", cutoff_hour)
      pipe.zcard(key_min)
      pipe.zcard(key_hour)
      pipe.zadd(key_min,  {str(now): now})
      pipe.zadd(key_hour, {str(now): now})
      pipe.expire(key_min,  int(_WINDOW_MINUTE) + 5)
      pipe.expire(key_hour, int(_WINDOW_HOUR)   + 5)
      results = pipe.execute()

      m_count = results[2]   # count after prune, before this request
      h_count = results[3]

      if m_count >= limits["minute"] * _EXTREME_MULTIPLIER:
          return _throttled(60, "Extreme request rate.", m_count, h_count)
      if m_count >= limits["minute"]:
          return _throttled(int(_WINDOW_MINUTE) + 1, "Minute limit.", m_count, h_count)
      if h_count >= limits["hour"]:
          return _throttled(int(_WINDOW_HOUR)   + 1, "Hour limit.",   m_count, h_count)
      return {"allowed": True, "throttled": False, "retry_after_seconds": 0,
              "reason": None, "requests_this_minute": m_count + 1,
              "requests_this_hour": h_count + 1}

Pre-conditions for enabling:
  1. Set REDIS_URL in Railway (or equivalent)
  2. Add redis to requirements.txt (redis>=5.0)
  3. Replace this module's implementation with the snippet above
  4. Test: two concurrent requests at limit N should both be counted correctly

No other files need changes — CEO calls check_rate_limit() by import.
────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from threading import Lock
from typing import Any, Optional

log = logging.getLogger("billing.rate_limiter")

# ---------------------------------------------------------------------------
# In-memory sliding window store
# ---------------------------------------------------------------------------

# {user_id: deque of timestamps (float)}
_MINUTE_WINDOW: dict[str, deque] = defaultdict(lambda: deque())
_HOUR_WINDOW:   dict[str, deque] = defaultdict(lambda: deque())
_LOCK = Lock()

_WINDOW_MINUTE = 60.0    # seconds
_WINDOW_HOUR   = 3600.0  # seconds

# ---------------------------------------------------------------------------
# Limits per tier
# ---------------------------------------------------------------------------

_LIMITS = {
    "free":  {"minute": 10, "hour": 60},
    "paid":  {"minute": 30, "hour": 200},
    "admin": {"minute": 9999, "hour": 99999},
    "max":   {"minute": 60,  "hour": 400},
}

_EXTREME_MULTIPLIER = 5   # 5× the minute limit triggers cooldown


def check_rate_limit(
    user_id:   str,
    user_tier: str = "free",
) -> dict[str, Any]:
    """
    Check whether this user is within rate limits.

    Returns:
      {
        allowed:             bool,
        throttled:           bool,   # True = 429 should be returned
        retry_after_seconds: int,    # 0 if allowed
        reason:              str | None,
        requests_this_minute: int,
        requests_this_hour:   int,
      }
    """
    tier   = user_tier.lower() if user_tier else "free"
    limits = _LIMITS.get(tier, _LIMITS["free"])
    now    = time.monotonic()

    with _LOCK:
        mq = _MINUTE_WINDOW[user_id]
        hq = _HOUR_WINDOW[user_id]

        # Prune expired entries
        while mq and now - mq[0] > _WINDOW_MINUTE:
            mq.popleft()
        while hq and now - hq[0] > _WINDOW_HOUR:
            hq.popleft()

        m_count = len(mq)
        h_count = len(hq)

        # Extreme burst — extended cooldown
        if m_count >= limits["minute"] * _EXTREME_MULTIPLIER:
            log.warning("rate_limiter: extreme burst user=%s count=%d", user_id, m_count)
            return _throttled(60, "Extreme request rate detected. Please wait 60 seconds.", m_count, h_count)

        # Minute limit
        if m_count >= limits["minute"]:
            retry = int(_WINDOW_MINUTE - (now - mq[0])) + 1
            log.info("rate_limiter: minute limit user=%s count=%d limit=%d", user_id, m_count, limits["minute"])
            return _throttled(retry, "Too many requests. Please slow down.", m_count, h_count)

        # Hour limit
        if h_count >= limits["hour"]:
            retry = int(_WINDOW_HOUR - (now - hq[0])) + 1
            log.info("rate_limiter: hour limit user=%s count=%d limit=%d", user_id, h_count, limits["hour"])
            return _throttled(retry, "Hourly request limit reached. Please try again later.", m_count, h_count)

        # Record this request
        mq.append(now)
        hq.append(now)

    return {
        "allowed":              True,
        "throttled":            False,
        "retry_after_seconds":  0,
        "reason":               None,
        "requests_this_minute": m_count + 1,
        "requests_this_hour":   h_count + 1,
    }


def _throttled(retry: int, reason: str, m_count: int, h_count: int) -> dict[str, Any]:
    return {
        "allowed":              False,
        "throttled":            True,
        "retry_after_seconds":  max(1, retry),
        "reason":               reason,
        "requests_this_minute": m_count,
        "requests_this_hour":   h_count,
    }


def get_usage_snapshot(user_id: str) -> dict[str, int]:
    """Return current request counts for a user (admin/debug use)."""
    now = time.monotonic()
    with _LOCK:
        mq = _MINUTE_WINDOW[user_id]
        hq = _HOUR_WINDOW[user_id]
        m_count = sum(1 for t in mq if now - t <= _WINDOW_MINUTE)
        h_count = sum(1 for t in hq if now - t <= _WINDOW_HOUR)
    return {"requests_this_minute": m_count, "requests_this_hour": h_count}
