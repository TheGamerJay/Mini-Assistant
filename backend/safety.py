"""
safety.py
Production hardening layer for Mini Assistant AI.

Covers:
  1.  Per-user rate limiting       — Redis-backed (in-memory fallback)
  2.  Cost protection              — max cost per request + max daily cost per user
  3.  Token protection             — max tokens per request
  4.  Abuse detection              — flag users with anomalous patterns
  5.  Alert system                 — margin/cost-spike warnings logged to DB
  6.  Subscription validation      — verify plan hasn't been cancelled in DB
  7.  Multi-stage enforcement      — warning → throttle → hard block
  8.  Global circuit breaker       — system-wide daily cost cap (HTTP 503)
  9.  Maintenance mode             — env-flag to block all non-admin traffic
  10. Token/cost consistency check — detect inflated cost claims
  11. Stripe fraud response        — cancel subscription on confirmed abuse
  12. Structured audit logging     — JSON-structured events for every violation
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Deque, Dict, Optional

from fastapi import HTTPException

log = logging.getLogger("safety")

# ---------------------------------------------------------------------------
# ── SAFE DEFAULT LIMITS (all overridable via env vars) ─────────────────────
# ---------------------------------------------------------------------------

def _int(key: str, default: int) -> int:
    try: return int(os.environ.get(key, default))
    except (ValueError, TypeError): return default

def _float(key: str, default: float) -> float:
    try: return float(os.environ.get(key, default))
    except (ValueError, TypeError): return default


# Per-user request caps (per plan)
MAX_RPM: Dict[str, int] = {          # requests per minute
    "free":     _int("RATE_FREE_RPM",     60),
    "standard": _int("RATE_STD_RPM",      60),
    "pro":      _int("RATE_PRO_RPM",      120),
    "team":     _int("RATE_TEAM_RPM",     240),
}
MAX_RPH: Dict[str, int] = {          # requests per hour
    "free":     _int("RATE_FREE_RPH",     200),
    "standard": _int("RATE_STD_RPH",      600),
    "pro":      _int("RATE_PRO_RPH",      1500),
    "team":     _int("RATE_TEAM_RPH",     4000),
}

# Cost caps
MAX_COST_PER_REQUEST_USD: float = _float("MAX_COST_PER_REQUEST_USD", 0.50)
MAX_DAILY_COST_USD: Dict[str, float] = {
    "free":     _float("MAX_DAILY_COST_FREE",     0.10),
    "standard": _float("MAX_DAILY_COST_STD",      2.00),
    "pro":      _float("MAX_DAILY_COST_PRO",      5.00),
    "team":     _float("MAX_DAILY_COST_TEAM",     20.00),
}

# Token caps (input + output tokens per single request)
MAX_TOKENS_PER_REQUEST: int = _int("MAX_TOKENS_PER_REQUEST", 50_000)

# Alert thresholds
MARGIN_ALERT_THRESHOLD: float     = _float("MARGIN_ALERT_THRESHOLD", 0.30)   # 30%
COST_SPIKE_MULTIPLIER:  float     = _float("COST_SPIKE_MULTIPLIER",  5.0)    # 5× avg
ABUSE_FLAG_THRESHOLD:   int       = _int("ABUSE_FLAG_THRESHOLD",     5)      # flags before action

# Periodic alert interval (seconds) — only run alert check this often
_ALERT_INTERVAL_S: int = _int("ALERT_INTERVAL_S", 300)   # every 5 min
_last_alert_run: float = 0.0

# ── Global circuit breaker ─────────────────────────────────────────────────
GLOBAL_MAX_DAILY_COST: float = _float("GLOBAL_MAX_DAILY_COST", 100.0)
_CIRCUIT_CHECK_INTERVAL: int = _int("CIRCUIT_CHECK_INTERVAL", 60)   # seconds

# ── Maintenance mode ───────────────────────────────────────────────────────
_MAINTENANCE_MODE: bool = os.environ.get("MAINTENANCE_MODE", "false").strip().lower() == "true"

# ── Multi-stage enforcement ────────────────────────────────────────────────
# Number of abuse flags in a 24-hour window required to reach each stage
ENFORCEMENT_STAGE_THRESHOLDS: dict[int, int] = {
    1: _int("ENFORCE_WARN_AT",    3),   # → warning
    2: _int("ENFORCE_THROTTLE_AT", 7),  # → throttled (50% rate limits)
    3: _int("ENFORCE_BLOCK_AT",   15),  # → hard block (HTTP 403)
}
ENFORCEMENT_STAGE_NAMES: dict[int, str] = {
    0: "clean", 1: "warning", 2: "throttled", 3: "blocked",
}
# Stage 2 throttle factor (multiplied against normal limits)
_THROTTLE_FACTOR: float = _float("ENFORCE_THROTTLE_FACTOR", 0.50)

# ── Token/cost consistency ─────────────────────────────────────────────────
# Max ratio between claimed_cost and recomputed cost before flagging
TOKEN_COST_TOLERANCE: float = _float("TOKEN_COST_TOLERANCE", 3.0)   # 3× leeway


# ---------------------------------------------------------------------------
# ── REDIS CLIENT (optional) ────────────────────────────────────────────────
# ---------------------------------------------------------------------------

_redis: object | None = None   # redis.asyncio.Redis instance
_redis_broken = False          # set True after first failure to stop retrying

async def _get_redis():
    global _redis, _redis_broken
    if _redis_broken:
        return None
    if _redis is not None:
        return _redis
    redis_url = os.environ.get("REDIS_URL", "")
    if not redis_url:
        return None
    try:
        import redis.asyncio as aioredis                        # noqa: PLC0415
        _redis = aioredis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        await _redis.ping()
        log.info("Safety: Redis connected at %s", redis_url.split("@")[-1])
        return _redis
    except Exception as exc:
        log.warning("Safety: Redis unavailable (%s) — using in-memory fallback", exc)
        _redis_broken = True
        return None


# ---------------------------------------------------------------------------
# ── IN-MEMORY FALLBACK RATE LIMITER ───────────────────────────────────────
# ---------------------------------------------------------------------------

class _MemWindow:
    """Sliding window counter keyed by arbitrary string (uid:window)."""

    def __init__(self) -> None:
        self._store: Dict[str, Deque[float]] = defaultdict(deque)

    def check_and_record(self, key: str, limit: int, window_s: int) -> bool:
        """Return True if request is allowed (and records it)."""
        now    = time.monotonic()
        cutoff = now - window_s
        dq     = self._store[key]
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= limit:
            return False
        dq.append(now)
        return True

    def retry_after(self, key: str, window_s: int) -> int:
        dq = self._store.get(key)
        if not dq:
            return 0
        return max(1, int(window_s - (time.monotonic() - dq[0])) + 1)

    def purge_old(self, max_age_s: int = 7200) -> None:
        """Remove buckets not touched in the last max_age_s seconds."""
        cutoff = time.monotonic() - max_age_s
        stale  = [k for k, dq in self._store.items() if (not dq or dq[-1] < cutoff)]
        for k in stale:
            del self._store[k]


_mem = _MemWindow()


async def _redis_rate_check(r, key: str, limit: int, window_s: int) -> tuple[bool, int]:
    """
    Sliding window via Redis ZADD/ZCOUNT.
    Returns (allowed, retry_after_seconds).
    """
    now     = int(time.time() * 1000)    # ms
    cutoff  = now - window_s * 1000

    pipe = r.pipeline()
    pipe.zremrangebyscore(key, "-inf", cutoff)
    pipe.zcard(key)
    pipe.zadd(key, {str(now): now})
    pipe.expire(key, window_s + 5)
    results = await pipe.execute()

    count_before_add = results[1]          # count before we added this request
    if count_before_add >= limit:
        # Roll back the add we just did
        await r.zrem(key, str(now))
        # Retry-after: time until the oldest entry expires
        oldest = await r.zrange(key, 0, 0, withscores=True)
        if oldest:
            _, score = oldest[0]
            retry = max(1, int((score + window_s * 1000 - now) / 1000) + 1)
        else:
            retry = 1
        return False, retry

    return True, 0


# ---------------------------------------------------------------------------
# ── PUBLIC: RATE LIMIT ENFORCEMENT ────────────────────────────────────────
# ---------------------------------------------------------------------------

async def enforce_rate_limit(uid: str, plan: str, action_type: str = "chat_message") -> None:
    """
    Check per-user rate limits (per minute and per hour).
    Raises HTTP 429 if exceeded.
    Stage-2 throttled users get 50% of their normal limits.
    """
    plan = plan if plan in MAX_RPM else "free"
    rpm_limit = MAX_RPM[plan]
    rph_limit = MAX_RPH[plan]

    # Apply throttle factor for stage-2 (throttled) users
    try:
        db = await _get_db_safe()
        stage, _ = await _get_enforcement_stage(uid, db)
        if stage >= 2:
            rpm_limit = max(1, int(rpm_limit * _THROTTLE_FACTOR))
            rph_limit = max(1, int(rph_limit * _THROTTLE_FACTOR))
    except Exception:
        pass   # never block on enforcement check failure

    r = await _get_redis()

    if r is not None:
        # Redis path — accurate across multiple workers
        try:
            min_key  = f"rl:uid:{uid}:1m"
            hour_key = f"rl:uid:{uid}:1h"

            ok_min,  retry_min  = await _redis_rate_check(r, min_key,  rpm_limit, 60)
            ok_hour, retry_hour = await _redis_rate_check(r, hour_key, rph_limit, 3600)

            if not ok_min:
                log.warning("Rate limit (1m): uid=%s plan=%s action=%s", uid, plan, action_type)
                await _maybe_flag(uid, "rate_limit_minute", {"plan": plan, "action": action_type})
                raise HTTPException(
                    429,
                    detail={
                        "error":       "rate_limit_exceeded",
                        "message":     f"Too many requests. Max {rpm_limit}/min for {plan} plan.",
                        "retry_after": retry_min,
                        "limit_type":  "per_minute",
                    },
                    headers={"Retry-After": str(retry_min)},
                )

            if not ok_hour:
                log.warning("Rate limit (1h): uid=%s plan=%s action=%s", uid, plan, action_type)
                await _maybe_flag(uid, "rate_limit_hour", {"plan": plan, "action": action_type})
                raise HTTPException(
                    429,
                    detail={
                        "error":       "rate_limit_exceeded",
                        "message":     f"Hourly request limit reached. Max {rph_limit}/hr for {plan} plan.",
                        "retry_after": retry_hour,
                        "limit_type":  "per_hour",
                    },
                    headers={"Retry-After": str(retry_hour)},
                )
            return

        except HTTPException:
            raise
        except Exception as exc:
            log.warning("Safety: Redis rate check failed (%s) — falling back to memory", exc)

    # In-memory fallback
    ok_min  = _mem.check_and_record(f"{uid}:1m",  rpm_limit, 60)
    ok_hour = _mem.check_and_record(f"{uid}:1h",  rph_limit, 3600)

    if not ok_min:
        retry = _mem.retry_after(f"{uid}:1m", 60)
        log.warning("Rate limit (mem/1m): uid=%s plan=%s", uid, plan)
        raise HTTPException(
            429,
            detail={
                "error":       "rate_limit_exceeded",
                "message":     f"Too many requests. Max {rpm_limit}/min for {plan} plan.",
                "retry_after": retry,
                "limit_type":  "per_minute",
            },
            headers={"Retry-After": str(retry)},
        )

    if not ok_hour:
        retry = _mem.retry_after(f"{uid}:1h", 3600)
        log.warning("Rate limit (mem/1h): uid=%s plan=%s", uid, plan)
        raise HTTPException(
            429,
            detail={
                "error":       "rate_limit_exceeded",
                "message":     f"Hourly request limit reached. Max {rph_limit}/hr for {plan} plan.",
                "retry_after": retry,
                "limit_type":  "per_hour",
            },
            headers={"Retry-After": str(retry)},
        )


# ---------------------------------------------------------------------------
# ── PUBLIC: COST LIMIT ENFORCEMENT ────────────────────────────────────────
# ---------------------------------------------------------------------------

async def enforce_cost_limit(
    uid: str,
    db,
    plan: str,
    estimated_cost_usd: float,
) -> None:
    """
    Check per-request and daily cost caps.
    Raises HTTP 402 (or 429) if exceeded.
    """
    plan = plan if plan in MAX_DAILY_COST_USD else "free"

    # ── 1. Per-request cost cap ───────────────────────────────────────────
    if estimated_cost_usd > MAX_COST_PER_REQUEST_USD:
        log.warning(
            "Cost cap (per-request): uid=%s cost=$%.4f limit=$%.2f",
            uid, estimated_cost_usd, MAX_COST_PER_REQUEST_USD,
        )
        await _flag_abuse(uid, db, "cost_per_request_exceeded", {
            "estimated_cost": estimated_cost_usd,
            "limit": MAX_COST_PER_REQUEST_USD,
        })
        raise HTTPException(
            400,
            detail={
                "error":   "request_too_expensive",
                "message": "Request exceeds maximum allowed cost. Please reduce input size.",
                "cost_usd": round(estimated_cost_usd, 4),
                "limit_usd": MAX_COST_PER_REQUEST_USD,
            },
        )

    # ── 2. Daily cost cap ─────────────────────────────────────────────────
    if db is None:
        return

    daily_limit = MAX_DAILY_COST_USD[plan]
    try:
        today_start = _today_epoch()
        agg = await db["activity_logs"].aggregate([
            {"$match": {"user_id": uid, "timestamp": {"$gte": today_start}}},
            {"$group": {"_id": None, "total": {"$sum": "$estimated_cost_usd"}}},
        ]).to_list(1)

        daily_cost = agg[0].get("total", 0.0) if agg else 0.0
        projected  = daily_cost + estimated_cost_usd

        if projected > daily_limit:
            log.warning(
                "Cost cap (daily): uid=%s spent=$%.4f + projected=$%.4f > limit=$%.2f",
                uid, daily_cost, estimated_cost_usd, daily_limit,
            )
            await _flag_abuse(uid, db, "daily_cost_exceeded", {
                "daily_cost":   round(daily_cost, 4),
                "projected":    round(projected, 4),
                "limit":        daily_limit,
                "plan":         plan,
            })
            raise HTTPException(
                429,
                detail={
                    "error":        "daily_cost_limit_reached",
                    "message":      "Daily AI usage limit reached. Resets at midnight UTC.",
                    "daily_cost":   round(daily_cost, 4),
                    "daily_limit":  daily_limit,
                },
            )
    except HTTPException:
        raise
    except Exception as exc:
        log.warning("Safety: daily cost check failed (%s) — allowing through", exc)


# ---------------------------------------------------------------------------
# ── PUBLIC: TOKEN LIMIT ENFORCEMENT ───────────────────────────────────────
# ---------------------------------------------------------------------------

def enforce_token_limit(tokens_in: int, tokens_out: int = 0) -> None:
    """
    Raise HTTP 400 if requested token counts exceed the per-request cap.
    Call this synchronously before making the AI API call.
    """
    total = tokens_in + tokens_out
    if total > MAX_TOKENS_PER_REQUEST:
        raise HTTPException(
            400,
            detail={
                "error":   "token_limit_exceeded",
                "message": f"Request exceeds maximum token limit ({MAX_TOKENS_PER_REQUEST:,} tokens).",
                "tokens":  total,
                "limit":   MAX_TOKENS_PER_REQUEST,
            },
        )


# ---------------------------------------------------------------------------
# ── PUBLIC: SUBSCRIPTION VALIDATION ───────────────────────────────────────
# ---------------------------------------------------------------------------

async def validate_subscription(uid: str, db, claimed_plan: str) -> str:
    """
    Cross-check the plan claimed in JWT against the DB record.
    Returns the DB plan (authoritative). Logs discrepancies.
    """
    if db is None:
        return claimed_plan
    try:
        user = await db["users"].find_one({"id": uid}, {"plan": 1, "stripe_subscription_id": 1})
        if not user:
            return claimed_plan
        db_plan = user.get("plan", "free") or "free"
        if db_plan != claimed_plan:
            log.warning(
                "Plan mismatch: uid=%s jwt_plan=%s db_plan=%s",
                uid, claimed_plan, db_plan,
            )
        return db_plan
    except Exception as exc:
        log.warning("Safety: subscription validation failed (%s)", exc)
        return claimed_plan


# ---------------------------------------------------------------------------
# ── PUBLIC: ABUSE DETECTION ────────────────────────────────────────────────
# ---------------------------------------------------------------------------

async def analyze_and_flag_abuse(uid: str, db) -> None:
    """
    Detect anomalous usage patterns and flag user if found.
    Lightweight — only reads the last 1-hour window.
    """
    if db is None:
        return
    try:
        hour_ago = time.time() - 3600
        agg = await db["activity_logs"].aggregate([
            {"$match": {"user_id": uid, "timestamp": {"$gte": hour_ago}}},
            {"$group": {
                "_id":       None,
                "count":     {"$sum": 1},
                "cost":      {"$sum": "$estimated_cost_usd"},
                "tokens_in": {"$sum": "$tokens_in"},
            }},
        ]).to_list(1)

        if not agg:
            return

        stats = agg[0]
        hourly_count   = stats.get("count", 0)
        hourly_cost    = stats.get("cost", 0.0)
        hourly_tokens  = stats.get("tokens_in", 0)

        flags = []
        if hourly_count  > 500:   flags.append(f"high_request_count:{hourly_count}")
        if hourly_cost   > 10.0:  flags.append(f"high_hourly_cost:${hourly_cost:.2f}")
        if hourly_tokens > 5_000_000: flags.append(f"high_token_usage:{hourly_tokens:,}")

        for reason in flags:
            await _flag_abuse(uid, db, reason, {
                "hourly_count":  hourly_count,
                "hourly_cost":   round(hourly_cost, 4),
                "hourly_tokens": hourly_tokens,
            })
    except Exception as exc:
        log.warning("Safety: abuse analysis failed (%s)", exc)


# ---------------------------------------------------------------------------
# ── PUBLIC: PERIODIC ALERT SYSTEM ─────────────────────────────────────────
# ---------------------------------------------------------------------------

async def run_periodic_alerts(db) -> None:
    """
    Check system-wide health metrics and log alerts.
    Called after every AI action but throttled to run at most once
    every ALERT_INTERVAL_S seconds (default 5 min).
    """
    global _last_alert_run
    now = time.time()
    if now - _last_alert_run < _ALERT_INTERVAL_S:
        return
    _last_alert_run = now

    # Run in background — never blocks the request
    asyncio.create_task(_run_alerts_background(db))


async def _run_alerts_background(db) -> None:
    """Background alert checks — never raises."""
    if db is None:
        return
    try:
        await _check_margin_alert(db)
        await _check_cost_spike(db)
        await _check_users_over_budget(db)
    except Exception as exc:
        log.warning("Safety: alert check error (%s)", exc)


async def _check_margin_alert(db) -> None:
    """Alert if current-month estimated profit margin drops below threshold."""
    month_key = _month_key()
    try:
        agg = await db["activity_logs"].aggregate([
            {"$match": {"month_key": month_key}},
            {"$group": {"_id": None, "total_cost": {"$sum": "$estimated_cost_usd"}}},
        ]).to_list(1)
        total_ai_cost = agg[0].get("total_cost", 0.0) if agg else 0.0

        # Estimate MRR from user plans
        from mini_credits import PLAN_MONTHLY_PRICE_USD   # noqa: PLC0415
        plan_pipeline = [
            {"$match": {"plan": {"$in": ["standard", "pro", "team"]}}},
            {"$group": {"_id": "$plan", "count": {"$sum": 1}}},
        ]
        plan_agg = await db["users"].aggregate(plan_pipeline).to_list(10)
        mrr = sum(
            PLAN_MONTHLY_PRICE_USD.get(row["_id"], 0) * row["count"]
            for row in plan_agg
        )

        if mrr > 0:
            margin = (mrr - total_ai_cost) / mrr
            if margin < MARGIN_ALERT_THRESHOLD:
                log.warning(
                    "MARGIN ALERT: margin=%.1f%% (MRR=$%.2f, AI cost=$%.2f) — "
                    "below %.0f%% threshold",
                    margin * 100, mrr, total_ai_cost, MARGIN_ALERT_THRESHOLD * 100,
                )
                await db["system_alerts"].insert_one({
                    "type":       "low_margin",
                    "month_key":  month_key,
                    "margin_pct": round(margin * 100, 2),
                    "mrr_usd":    round(mrr, 2),
                    "ai_cost_usd": round(total_ai_cost, 4),
                    "timestamp":  time.time(),
                })
    except Exception as exc:
        log.warning("Safety: margin alert check failed (%s)", exc)


async def _check_cost_spike(db) -> None:
    """Alert if today's cost is significantly higher than rolling 7-day average."""
    try:
        seven_days_ago = time.time() - 7 * 86400
        today_start    = _today_epoch()

        # 7-day daily costs
        weekly_agg = await db["activity_logs"].aggregate([
            {"$match": {"timestamp": {"$gte": seven_days_ago, "$lt": today_start}}},
            {"$group": {"_id": None, "total": {"$sum": "$estimated_cost_usd"}, "n": {"$sum": 1}}},
        ]).to_list(1)

        if not weekly_agg or weekly_agg[0].get("n", 0) == 0:
            return

        seven_day_total = weekly_agg[0].get("total", 0.0)
        daily_avg       = seven_day_total / 7.0

        # Today's cost
        today_agg = await db["activity_logs"].aggregate([
            {"$match": {"timestamp": {"$gte": today_start}}},
            {"$group": {"_id": None, "total": {"$sum": "$estimated_cost_usd"}}},
        ]).to_list(1)
        today_cost = today_agg[0].get("total", 0.0) if today_agg else 0.0

        if daily_avg > 0 and today_cost > daily_avg * COST_SPIKE_MULTIPLIER:
            log.warning(
                "COST SPIKE ALERT: today=$%.4f vs 7d_avg=$%.4f (%.1f×)",
                today_cost, daily_avg, today_cost / daily_avg,
            )
            await db["system_alerts"].insert_one({
                "type":        "cost_spike",
                "today_usd":   round(today_cost, 4),
                "avg_7d_usd":  round(daily_avg, 4),
                "multiplier":  round(today_cost / daily_avg, 2),
                "timestamp":   time.time(),
            })
    except Exception as exc:
        log.warning("Safety: cost spike check failed (%s)", exc)


async def _check_users_over_budget(db) -> None:
    """Flag users whose today's AI cost exceeds their plan revenue."""
    try:
        from mini_credits import PLAN_MONTHLY_PRICE_USD   # noqa: PLC0415
        today_start = _today_epoch()
        daily_revenue_by_plan = {
            plan: price / 30.0
            for plan, price in PLAN_MONTHLY_PRICE_USD.items()
        }

        # Aggregate today's cost per user
        agg = await db["activity_logs"].aggregate([
            {"$match": {"timestamp": {"$gte": today_start}, "estimated_cost_usd": {"$gt": 0}}},
            {"$group": {
                "_id":   "$user_id",
                "cost":  {"$sum": "$estimated_cost_usd"},
                "plan":  {"$last": "$plan"},
            }},
        ]).to_list(1000)

        for row in agg:
            uid       = row["_id"]
            cost      = row.get("cost", 0.0)
            user_plan = row.get("plan", "free") or "free"
            rev       = daily_revenue_by_plan.get(user_plan, 0.0)

            if cost > 0 and (rev == 0 or cost > rev * 2):
                await _flag_abuse(uid, db, "user_cost_exceeds_revenue", {
                    "daily_cost_usd":    round(cost, 4),
                    "daily_revenue_est": round(rev, 4),
                    "plan":              user_plan,
                })
    except Exception as exc:
        log.warning("Safety: budget check failed (%s)", exc)


# ---------------------------------------------------------------------------
# ── INTERNAL HELPERS ───────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

_recent_flags: Dict[str, list[float]] = defaultdict(list)   # uid → list of flag timestamps


async def _maybe_flag(uid: str, reason: str, details: dict) -> None:
    """Record a rate-limit flag without touching DB (lightweight)."""
    now = time.time()
    window = _recent_flags[uid]
    window.append(now)
    # Keep only last hour
    cutoff = now - 3600
    _recent_flags[uid] = [t for t in window if t > cutoff]

    if len(_recent_flags[uid]) >= ABUSE_FLAG_THRESHOLD:
        # Escalate to DB
        db = await _get_db_safe()
        if db:
            await _flag_abuse(uid, db, f"repeated_{reason}", {
                "count": len(_recent_flags[uid]),
                **details,
            })


async def _flag_abuse(uid: str, db, reason: str, details: dict) -> None:
    """
    Write or update an abuse flag record in the `abuse_flags` collection.
    After writing, escalate the user's enforcement stage.
    Non-fatal — never raises.
    """
    if db is None:
        return
    try:
        await db["abuse_flags"].update_one(
            {"user_id": uid, "reason": reason},
            {
                "$set":  {"last_seen": time.time(), "details": details},
                "$inc":  {"count": 1},
                "$setOnInsert": {
                    "user_id":    uid,
                    "reason":     reason,
                    "first_seen": time.time(),
                    "actioned":   False,
                },
            },
            upsert=True,
        )
        _audit("abuse_flag", uid=uid, extra={"reason": reason, **{k: v for k, v in details.items() if not isinstance(v, (dict, list))}})
        log.warning("Abuse flag: uid=%s reason=%s", uid, reason)

        # Escalate enforcement stage based on total flags
        await escalate_enforcement(uid, db, reason)

    except Exception as exc:
        log.warning("Safety: flag_abuse write failed (%s)", exc)


async def _get_db_safe():
    try:
        import server as _srv   # noqa: PLC0415
        return _srv.db
    except Exception:
        return None


def _month_key() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.year:04d}-{now.month:02d}"


def _today_epoch() -> float:
    """Unix timestamp for start of today (UTC)."""
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, now.day, tzinfo=timezone.utc).timestamp()


# ---------------------------------------------------------------------------
# ── MAINTENANCE MODE ───────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

def check_maintenance_mode(role: str = "") -> None:
    """
    Raise HTTP 503 if MAINTENANCE_MODE=true and the requester is not an admin.
    Call this at the very start of any user-facing endpoint.
    """
    if _MAINTENANCE_MODE and role != "admin":
        _audit("maintenance_block", uid="anonymous", extra={"role": role})
        raise HTTPException(
            503,
            detail={
                "error":   "maintenance_mode",
                "message": "Mini Assistant is undergoing maintenance. Please try again shortly.",
            },
        )


# ---------------------------------------------------------------------------
# ── GLOBAL CIRCUIT BREAKER ─────────────────────────────────────────────────
# ---------------------------------------------------------------------------

_circuit_state: dict = {"tripped": False, "checked_at": 0.0, "daily_cost": 0.0}


async def check_global_circuit_breaker(db) -> None:
    """
    Block all AI requests if system-wide daily AI cost exceeds GLOBAL_MAX_DAILY_COST.
    Cached for _CIRCUIT_CHECK_INTERVAL seconds to avoid hitting DB on every request.
    Raises HTTP 503 when tripped.
    """
    now = time.time()
    if now - _circuit_state["checked_at"] < _CIRCUIT_CHECK_INTERVAL:
        # Use cached state
        if _circuit_state["tripped"]:
            _audit("circuit_breaker_block", uid="system",
                   extra={"daily_cost": _circuit_state["daily_cost"], "limit": GLOBAL_MAX_DAILY_COST})
            raise HTTPException(
                503,
                detail={
                    "error":   "global_cost_limit",
                    "message": "AI services temporarily unavailable due to high usage. Try again later.",
                    "daily_cost":  round(_circuit_state["daily_cost"], 2),
                    "daily_limit": GLOBAL_MAX_DAILY_COST,
                },
            )
        return

    _circuit_state["checked_at"] = now

    if db is None:
        return

    try:
        today_start = _today_epoch()
        agg = await db["activity_logs"].aggregate([
            {"$match": {"timestamp": {"$gte": today_start}, "estimated_cost_usd": {"$gt": 0}}},
            {"$group": {"_id": None, "total": {"$sum": "$estimated_cost_usd"}}},
        ]).to_list(1)
        daily_cost = agg[0].get("total", 0.0) if agg else 0.0
        _circuit_state["daily_cost"] = daily_cost

        if daily_cost >= GLOBAL_MAX_DAILY_COST:
            _circuit_state["tripped"] = True
            log.critical(
                "CIRCUIT BREAKER TRIPPED: daily_cost=$%.2f >= limit=$%.2f — AI endpoints DISABLED",
                daily_cost, GLOBAL_MAX_DAILY_COST,
            )
            # Persist alert to DB (best-effort)
            try:
                await db["system_alerts"].insert_one({
                    "type":        "circuit_breaker_tripped",
                    "daily_cost":  round(daily_cost, 4),
                    "limit":       GLOBAL_MAX_DAILY_COST,
                    "timestamp":   now,
                })
            except Exception:
                pass
            raise HTTPException(
                503,
                detail={
                    "error":   "global_cost_limit",
                    "message": "AI services temporarily unavailable due to high usage. Try again later.",
                    "daily_cost":  round(daily_cost, 2),
                    "daily_limit": GLOBAL_MAX_DAILY_COST,
                },
            )
        else:
            _circuit_state["tripped"] = False

    except HTTPException:
        raise
    except Exception as exc:
        log.warning("Circuit breaker check failed (%s) — allowing through", exc)


# ---------------------------------------------------------------------------
# ── MULTI-STAGE ENFORCEMENT (soft lock → hard block) ──────────────────────
# ---------------------------------------------------------------------------

async def _get_enforcement_stage(uid: str, db) -> tuple[int, str]:
    """
    Read user's current enforcement stage from DB.
    Returns (stage: 0-3, reason: str).
    Non-fatal — returns (0, "") on any error.
    """
    if db is None:
        return 0, ""
    try:
        doc = await db["user_enforcement"].find_one(
            {"user_id": uid},
            {"stage": 1, "reason": 1, "cleared_at": 1},
        )
        if not doc:
            return 0, ""
        if doc.get("cleared_at"):
            return 0, ""   # admin-cleared
        return int(doc.get("stage", 0)), doc.get("reason", "")
    except Exception as exc:
        log.warning("Enforcement stage lookup failed for uid=%s: %s", uid, exc)
        return 0, ""


async def check_enforcement_status(uid: str, db) -> tuple[int, str]:
    """
    Public: return (stage, reason) for a user. Use in admin APIs.
    """
    return await _get_enforcement_stage(uid, db)


async def enforce_hard_block(uid: str, db) -> None:
    """
    Raise HTTP 403 if user is at enforcement stage 3 (hard blocked).
    Call this AFTER rate-limit checks in check_and_deduct.
    """
    stage, reason = await _get_enforcement_stage(uid, db)
    if stage >= 3:
        _audit("hard_block_enforced", uid=uid, extra={"reason": reason})
        raise HTTPException(
            403,
            detail={
                "error":   "account_blocked",
                "message": "Your account has been restricted due to policy violations. Contact support.",
                "reason":  reason,
            },
        )


async def escalate_enforcement(uid: str, db, reason: str) -> int:
    """
    Increment the user's enforcement stage based on 24-hour flag count.
    Returns the new stage (0-3).
    Also triggers Stripe subscription cancellation at stage 3.
    Non-fatal — logs errors but does not raise.
    """
    if db is None:
        return 0
    try:
        # Count abuse flags in last 24 hours
        since = time.time() - 86400
        flag_count = await db["abuse_flags"].count_documents({
            "user_id": uid,
            "last_seen": {"$gte": since},
        })

        new_stage = 0
        for stage in sorted(ENFORCEMENT_STAGE_THRESHOLDS, reverse=True):
            if flag_count >= ENFORCEMENT_STAGE_THRESHOLDS[stage]:
                new_stage = stage
                break

        stage_name = ENFORCEMENT_STAGE_NAMES.get(new_stage, "unknown")

        # Upsert enforcement record
        await db["user_enforcement"].update_one(
            {"user_id": uid},
            {
                "$set": {
                    "stage":        new_stage,
                    "stage_name":   stage_name,
                    "flag_count":   flag_count,
                    "reason":       reason,
                    "updated_at":   time.time(),
                },
                "$setOnInsert": {
                    "user_id":     uid,
                    "created_at":  time.time(),
                    "cleared_at":  None,
                    "stripe_cancelled": False,
                },
            },
            upsert=True,
        )

        _audit(f"enforcement_stage_{new_stage}", uid=uid, extra={
            "stage":       new_stage,
            "stage_name":  stage_name,
            "flag_count":  flag_count,
            "reason":      reason,
        })

        log.warning(
            "Enforcement: uid=%s → stage=%d (%s) flags_24h=%d reason=%s",
            uid, new_stage, stage_name, flag_count, reason,
        )

        # Stage 3: hard block → cancel Stripe subscription
        if new_stage >= 3:
            asyncio.create_task(_cancel_stripe_for_abuse(uid, db))

        return new_stage

    except Exception as exc:
        log.warning("Enforcement escalation failed for uid=%s: %s", uid, exc)
        return 0


async def _cancel_stripe_for_abuse(uid: str, db) -> None:
    """
    Cancel the user's Stripe subscription immediately due to abuse.
    Also downgrades their plan in DB without waiting for the webhook.
    Non-fatal — logs errors.
    """
    try:
        import stripe as _stripe   # noqa: PLC0415

        user = await db["users"].find_one(
            {"id": uid},
            {"stripe_subscription_id": 1, "plan": 1, "email": 1},
        )
        if not user:
            return

        old_plan = user.get("plan", "free")
        sub_id   = user.get("stripe_subscription_id")

        # Immediate DB downgrade (don't wait for webhook)
        await db["users"].update_one(
            {"id": uid},
            {"$set": {
                "plan":                   "free",
                "subscription_credits":   50,
                "stripe_subscription_id": None,
                "abuse_blocked_at":       time.time(),
                "abuse_block_reason":     "enforcement_stage_3",
            }},
        )

        # Cancel in Stripe (triggers subscription.deleted webhook for idempotent cleanup)
        if sub_id and _stripe.api_key:
            try:
                _stripe.Subscription.delete(sub_id)
                log.warning(
                    "FRAUD RESPONSE: cancelled Stripe sub=%s for uid=%s (was plan=%s)",
                    sub_id, uid, old_plan,
                )
            except _stripe.error.InvalidRequestError as exc:
                # Already cancelled — fine
                log.info("Stripe sub %s already cancelled: %s", sub_id, exc)
            except Exception as exc:
                log.error("Stripe cancellation failed for uid=%s sub=%s: %s", uid, sub_id, exc)

        # Mark enforcement record
        await db["user_enforcement"].update_one(
            {"user_id": uid},
            {"$set": {"stripe_cancelled": True, "stripe_cancelled_at": time.time()}},
        )

        _audit("stripe_fraud_response", uid=uid, extra={
            "sub_id":   sub_id,
            "old_plan": old_plan,
        })

        log.warning(
            "ABUSE RESPONSE: uid=%s plan %s → free + Stripe cancelled",
            uid, old_plan,
        )

    except Exception as exc:
        log.error("_cancel_stripe_for_abuse failed for uid=%s: %s", uid, exc)


# ---------------------------------------------------------------------------
# ── TOKEN / COST CONSISTENCY CHECK ────────────────────────────────────────
# ---------------------------------------------------------------------------

async def validate_token_cost_consistency(
    tokens_in: int,
    tokens_out: int,
    claimed_cost_usd: float,
    uid: str,
    db,
) -> None:
    """
    Cross-check claimed USD cost against token-derived cost.
    Flags (and optionally blocks) if the ratio is outside tolerance.
    Non-fatal — logs but does not raise unless anomaly is extreme (10×).
    """
    if tokens_in <= 0 and tokens_out <= 0:
        return   # no token data — cannot validate

    TOKEN_IN_RATE  = 3.00 / 1_000_000
    TOKEN_OUT_RATE = 15.00 / 1_000_000
    recomputed = tokens_in * TOKEN_IN_RATE + tokens_out * TOKEN_OUT_RATE

    if recomputed <= 0:
        return

    ratio = claimed_cost_usd / recomputed

    if ratio > TOKEN_COST_TOLERANCE:
        details = {
            "claimed_cost":  round(claimed_cost_usd, 6),
            "recomputed":    round(recomputed, 6),
            "ratio":         round(ratio, 2),
            "tokens_in":     tokens_in,
            "tokens_out":    tokens_out,
        }
        _audit("token_cost_mismatch", uid=uid, extra=details)
        log.warning(
            "Token/cost mismatch: uid=%s claimed=$%.5f recomputed=$%.5f ratio=%.1f×",
            uid, claimed_cost_usd, recomputed, ratio,
        )
        if db:
            await _flag_abuse(uid, db, "token_cost_mismatch", details)

        # Extreme mismatch (10×) — block the request
        if ratio > TOKEN_COST_TOLERANCE * 10:
            raise HTTPException(
                400,
                detail={
                    "error":   "cost_validation_failed",
                    "message": "Request cost validation failed. Please contact support.",
                },
            )


# ---------------------------------------------------------------------------
# ── FEATURE GATING ─────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

# Features locked to paid plans
_PLAN_RANK: dict[str, int] = {"free": 0, "standard": 1, "pro": 2, "max": 3, "team": 3}

# action_type → minimum plan rank required
FEATURE_PLAN_REQUIREMENTS: dict[str, int] = {
    "export_zip":      1,   # standard+
    "github_push":     1,   # standard+
    "deploy_vercel":   2,   # pro+
    "app_build":       0,   # free (but truncated)
    "code_review":     0,   # free
    "image_generated": 0,   # free
    "chat_message":    0,   # free
}


def require_plan(action_type: str, user_plan: str) -> None:
    """
    Raise HTTP 403 if user_plan doesn't meet the minimum for action_type.
    Call this before any feature-gated operation.
    """
    min_rank    = FEATURE_PLAN_REQUIREMENTS.get(action_type, 0)
    user_rank   = _PLAN_RANK.get(user_plan, 0)
    if user_rank < min_rank:
        needed = [p for p, r in _PLAN_RANK.items() if r >= min_rank and p != "free"]
        _audit("feature_gate_blocked", uid="unknown", extra={
            "action": action_type, "user_plan": user_plan,
            "required_rank": min_rank,
        })
        raise HTTPException(
            403,
            detail={
                "error":    "plan_required",
                "message":  f"This feature requires a paid plan.",
                "action":   action_type,
                "required": needed[:2],
                "upgrade":  "/pricing",
            },
        )


# ---------------------------------------------------------------------------
# ── STRUCTURED AUDIT LOGGING ───────────────────────────────────────────────
# ---------------------------------------------------------------------------

import json as _json

_audit_log = logging.getLogger("safety.audit")


def _audit(event: str, uid: str, extra: dict | None = None) -> None:
    """
    Emit a structured JSON audit log line.
    These are machine-parseable and can be shipped to a log aggregator.
    """
    record = {
        "event":     event,
        "uid":       uid,
        "timestamp": time.time(),
        "ts_iso":    datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        record.update(extra)
    _audit_log.warning(_json.dumps(record))


# ---------------------------------------------------------------------------
# ── STARTUP SECURITY CHECKS ────────────────────────────────────────────────
# ---------------------------------------------------------------------------

def run_startup_security_checks() -> None:
    """
    Log warnings for any insecure or missing configuration at startup.
    Call once during app startup.
    """
    import hashlib

    checks_passed = 0
    checks_total  = 0

    def _check(condition: bool, warning: str, critical: bool = False) -> None:
        nonlocal checks_passed, checks_total
        checks_total += 1
        if condition:
            checks_passed += 1
        else:
            lvl = log.critical if critical else log.warning
            lvl("SECURITY CHECK FAILED: %s", warning)

    # Stripe
    _check(bool(os.environ.get("STRIPE_SECRET_KEY")),
           "STRIPE_SECRET_KEY is not set — payment processing disabled", critical=True)
    _check(bool(os.environ.get("STRIPE_WEBHOOK_SECRET")),
           "STRIPE_WEBHOOK_SECRET is not set — webhooks cannot be verified", critical=True)

    # JWT
    jwt_secret = os.environ.get("JWT_SECRET", "mini_assistant_jwt_secret_2025")
    _check(jwt_secret != "mini_assistant_jwt_secret_2025",
           "JWT_SECRET is using the insecure default — tokens can be forged", critical=True)
    _check(len(jwt_secret) >= 32,
           f"JWT_SECRET is too short ({len(jwt_secret)} chars) — use 32+ random bytes")

    # MongoDB
    _check(bool(os.environ.get("MONGO_URL")),
           "MONGO_URL is not set — all database features disabled", critical=True)

    # Global safety limits
    _check(GLOBAL_MAX_DAILY_COST < 1000,
           f"GLOBAL_MAX_DAILY_COST=${GLOBAL_MAX_DAILY_COST} seems very high — verify this is intentional")

    # Redis (non-critical)
    if not os.environ.get("REDIS_URL"):
        log.info("SECURITY INFO: REDIS_URL not set — using in-memory rate limiting (single-process only)")

    # Maintenance mode
    if _MAINTENANCE_MODE:
        log.warning("MAINTENANCE MODE IS ACTIVE — all non-admin requests will return 503")

    log.info("Security checks: %d/%d passed", checks_passed, checks_total)


# ---------------------------------------------------------------------------
# ── STARTUP: periodic memory purge ────────────────────────────────────────
# ---------------------------------------------------------------------------

async def start_background_tasks() -> None:
    """Call once at app startup to start maintenance loops."""
    asyncio.create_task(_purge_loop())
    asyncio.create_task(_circuit_reset_loop())


async def _purge_loop() -> None:
    """Periodically evict stale in-memory rate limit buckets."""
    while True:
        await asyncio.sleep(600)   # every 10 min
        try:
            _mem.purge_old()
        except Exception:
            pass


async def _circuit_reset_loop() -> None:
    """Reset circuit breaker check interval at midnight UTC so new day resets."""
    while True:
        now  = datetime.now(timezone.utc)
        secs = 86400 - (now.hour * 3600 + now.minute * 60 + now.second)
        await asyncio.sleep(max(secs, 1))
        _circuit_state["checked_at"] = 0.0   # force re-check at next request
        log.info("Circuit breaker: daily counter reset at midnight UTC")
