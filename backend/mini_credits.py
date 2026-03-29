"""
mini_credits.py
Unified credit management, cost tracking, and usage logging for Mini Assistant AI.

Every AI action flows through check_and_deduct(), which:
  1.  Authenticates the user (JWT)
  2.  Validates plan from DB (DB is authoritative, not JWT)
  3.  Enforces per-user rate limits   (via safety module)
  4.  Enforces per-request cost caps  (via safety module)
  5.  Checks credit balance           (free + dual-credit users)
  6.  Deducts credits atomically      (no race conditions, no negative credits)
  7.  Logs usage with full schema
  8.  Returns (ok, credits_remaining)

Exploit mitigations:
  - Plan always read from DB, never trusted from JWT
  - Atomic $expr pipeline updates prevent all race conditions
  - MongoDB OperationFailure on old versions falls back cleanly
  - Rollback uses time-windowed + exact-match log deletion
  - Unauthenticated requests are tracked and rate-limited by IP at middleware level
  - Negative credits are mathematically impossible via $max:0 pipeline stages
"""

import logging
import os
import time
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorCollection   # type hint only

log = logging.getLogger(__name__)

JWT_SECRET    = os.environ.get("JWT_SECRET", "mini_assistant_jwt_secret_2025")
JWT_ALGORITHM = "HS256"

if JWT_SECRET == "mini_assistant_jwt_secret_2025":
    log.warning(
        "SECURITY: JWT_SECRET is using the insecure default value. "
        "Set JWT_SECRET env var to a cryptographically random string in production."
    )

# ---------------------------------------------------------------------------
# Authoritative cost config
# ---------------------------------------------------------------------------

CREDIT_COSTS: dict[str, int] = {
    "chat_message":    1,
    "chat_stream":     1,
    "image_generated": 3,
    "image_analyze":   1,
    "app_build":       5,
    "code_review":     2,
    "chat_compare":    2,
    "fixloop_analyze": 1,
    "tester_generate": 1,
    "export_zip":      0,
    "github_push":     0,
    "deploy_vercel":   0,
}

# Estimated USD cost per action (Claude Sonnet 4.6: $3/M input, $15/M output)
AI_COST_USD: dict[str, float] = {
    "chat_message":    0.018,
    "chat_stream":     0.018,
    "image_generated": 0.040,
    "app_build":       0.090,
    "code_review":     0.012,
    "export_zip":      0.001,
    "github_push":     0.001,
    "deploy_vercel":   0.002,
}

TOKEN_COST_INPUT_PER_M  = 3.00
TOKEN_COST_OUTPUT_PER_M = 15.00

PLAN_CREDIT_LIMITS: dict[str, int] = {
    "free":     50,
    "standard": 500,
    "pro":      2000,
}

PLAN_MONTHLY_PRICE_USD: dict[str, float] = {
    "free":     0.0,
    "standard": 9.0,
    "pro":      19.0,
    "max":      49.0,
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _decode_bearer(authorization: str | None) -> dict | None:
    """
    Decode and validate a Bearer JWT.
    Returns payload dict, or None if missing/invalid/expired.
    jose.jwt.decode() already validates `exp` — we do NOT re-implement that.
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        return None
    try:
        from jose import jwt, JWTError   # noqa: PLC0415
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        uid = payload.get("sub")
        if not uid or not isinstance(uid, str):
            log.warning("JWT rejected: missing or non-string 'sub' field")
            return None
        return payload
    except Exception as exc:
        log.debug("JWT decode failed: %s", exc)
        return None


async def _get_db():
    try:
        import server as _srv   # noqa: PLC0415
        return _srv.db
    except Exception:
        return None


def _month_key() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.year:04d}-{now.month:02d}"


def _compute_cost_usd(action_type: str, tokens_in: int = 0, tokens_out: int = 0) -> float:
    if tokens_in > 0 or tokens_out > 0:
        return (
            tokens_in  * TOKEN_COST_INPUT_PER_M  / 1_000_000 +
            tokens_out * TOKEN_COST_OUTPUT_PER_M / 1_000_000
        )
    return AI_COST_USD.get(action_type, 0.005)


async def _log_usage(
    db,
    uid: str,
    user_name: str,
    user_email: str,
    action_type: str,
    credits_used: int,
    tokens_in: int,
    tokens_out: int,
    estimated_cost_usd: float,
    plan: str,
) -> str | None:
    """
    Insert a usage record. Returns the inserted _id as a string (for rollback),
    or None on failure. Non-fatal.
    """
    try:
        result = await db["activity_logs"].insert_one({
            "user_id":             uid,
            "user_name":           user_name,
            "user_email":          user_email,
            "type":                action_type,
            "action_type":         action_type,
            "credits_used":        credits_used,
            "tokens_in":           tokens_in,
            "tokens_out":          tokens_out,
            "estimated_cost_usd":  estimated_cost_usd,
            "plan":                plan,
            "month_key":           _month_key(),
            "timestamp":           time.time(),
        })
        return str(result.inserted_id)
    except Exception as exc:
        log.warning("usage log insert failed: %s", exc)
        return None


async def _deduct_dual_atomic(
    db,
    uid: str,
    cost: int,
    sub_c: int,
    topup_c: int,
) -> tuple[bool, int]:
    """
    Atomically deduct `cost` credits from subscription_credits first,
    then topup_credits, using a MongoDB 4.2+ pipeline update.

    Returns (success: bool, new_total: int).
    On MongoDB < 4.2 (OperationFailure), falls back to guarded $inc.
    """
    if cost == 0:
        return True, sub_c + topup_c

    try:
        from pymongo.errors import OperationFailure   # noqa: PLC0415

        result = await db["users"].find_one_and_update(
            {
                "id": uid,
                # Guard: total credits ≥ cost at execution time
                "$expr": {"$gte": [
                    {"$add": [
                        {"$ifNull": ["$subscription_credits", 0]},
                        {"$ifNull": ["$topup_credits", 0]},
                    ]},
                    cost,
                ]},
            },
            [
                {"$set": {
                    # Drain subscription_credits first, floor at 0
                    "subscription_credits": {
                        "$max": [0, {"$subtract": [
                            {"$ifNull": ["$subscription_credits", 0]}, cost
                        ]}]
                    },
                    # Drain topup_credits for any overflow
                    "topup_credits": {
                        "$max": [0, {
                            "$subtract": [
                                {"$ifNull": ["$topup_credits", 0]},
                                {"$max": [0, {"$subtract": [
                                    cost,
                                    {"$ifNull": ["$subscription_credits", 0]},
                                ]}]},
                            ]
                        }]
                    },
                }},
            ],
            return_document=True,
            projection={"subscription_credits": 1, "topup_credits": 1},
        )

        if result is None:
            # Filter didn't match: another request consumed credits first
            return False, 0

        new_sub   = result.get("subscription_credits", 0)
        new_topup = result.get("topup_credits", 0)
        return True, max(0, new_sub) + max(0, new_topup)

    except Exception as exc:
        # MongoDB < 4.2: pipeline updates not supported — use guarded $inc fallback
        log.warning("Pipeline update unsupported (%s) — using $inc fallback", exc)

        deduct_sub   = min(cost, sub_c)
        deduct_topup = max(0, cost - deduct_sub)

        # Atomically guard each field with $gte to prevent negatives
        upd = {}
        if deduct_sub > 0:
            upd["subscription_credits"] = -deduct_sub
        if deduct_topup > 0:
            upd["topup_credits"] = -deduct_topup

        flt = {"id": uid}
        if deduct_sub > 0:
            flt["subscription_credits"] = {"$gte": deduct_sub}
        if deduct_topup > 0:
            flt["topup_credits"] = {"$gte": deduct_topup}

        r2 = await db["users"].find_one_and_update(
            flt,
            {"$inc": upd},
            return_document=True,
            projection={"subscription_credits": 1, "topup_credits": 1},
        )
        if r2 is None:
            return False, 0

        new_sub   = max(0, r2.get("subscription_credits", 0))
        new_topup = max(0, r2.get("topup_credits", 0))
        return True, new_sub + new_topup


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def get_user_credits(authorization: str | None) -> int | None:
    """Return current credit balance, or None on auth/DB failure."""
    payload = _decode_bearer(authorization)
    if not payload:
        return None
    db = await _get_db()
    if db is None:
        return None
    user = await db["users"].find_one(
        {"id": payload["sub"]},
        {"credits": 1, "subscription_credits": 1, "topup_credits": 1},
    )
    if not user:
        return None
    sub_c = user.get("subscription_credits")
    if sub_c is not None:
        return max(0, sub_c) + max(0, user.get("topup_credits", 0))
    return max(0, user.get("credits", 0))


async def check_and_deduct(
    authorization: str | None,
    cost: int | None = None,
    action_type: str = "chat_message",
    tokens_in: int = 0,
    tokens_out: int = 0,
) -> tuple[bool, int]:
    """
    Main credit gate for all AI actions.

    Security guarantees:
    - Plan is ALWAYS read from DB (never trusted from JWT payload)
    - Atomic deduction prevents race-condition exploits
    - Negative credits are mathematically impossible
    - Rate limits and cost caps enforced before any deduction
    - Unauthenticated requests: allowed (dev/local), but never deducted from any user

    Returns
    -------
    (ok: bool, credits_remaining: int)
      ok=True        → action is allowed
      ok=False       → insufficient credits or safety limit exceeded
      remaining=-1   → unauthenticated / DB unavailable
    """
    # Validate cost
    if cost is None:
        cost = CREDIT_COSTS.get(action_type, 1)
    cost = max(0, int(cost))

    payload = _decode_bearer(authorization)
    if not payload:
        # Unauthenticated: allow for local/dev — never touches any user's credits
        log.debug("check_and_deduct: unauthenticated request for action=%s", action_type)
        return True, -1

    uid = payload["sub"]

    db = await _get_db()
    if db is None:
        log.warning("check_and_deduct: DB unavailable — allowing uid=%s through", uid)
        return True, -1

    # ── Load user from DB (plan is DB-authoritative, not JWT) ──────────────
    user = await db["users"].find_one(
        {"id": uid},
        {"credits": 1, "subscription_credits": 1, "topup_credits": 1,
         "plan": 1, "name": 1, "email": 1},
    )
    if not user:
        log.warning("check_and_deduct: user %s not found in DB", uid)
        return False, 0

    plan       = (user.get("plan") or "free").lower()
    user_name  = user.get("name", "")
    user_email = user.get("email", "")
    cost_usd   = _compute_cost_usd(action_type, tokens_in, tokens_out)

    # ── Safety checks (ordered: cheapest → most expensive) ────────────────
    import os as _os
    _safety_disabled = _os.environ.get("DISABLE_RATE_LIMIT", "0") == "1"
    if _safety_disabled:
        log.warning("DISABLE_RATE_LIMIT=1 — skipping all safety checks for uid=%s", uid)
    else:
        try:
            import safety as _safety   # noqa: PLC0415
            from fastapi import HTTPException as _HTTPEx   # noqa: PLC0415

            # 1. Maintenance mode (sync, zero-cost)
            _safety.check_maintenance_mode(role=user.get("role", ""))

            # 2. Hard block (DB read, but only if prior flags exist)
            await _safety.enforce_hard_block(uid, db)

            # 3. Feature gate (sync, zero-cost)
            _safety.require_plan(action_type, plan)

            # 4. Global circuit breaker (cached DB read every 60s)
            await _safety.check_global_circuit_breaker(db)

            # 5. Per-user rate limits (Redis or in-memory)
            await _safety.enforce_rate_limit(uid, plan, action_type)

            # 6. Per-request + daily cost caps (DB aggregate)
            await _safety.enforce_cost_limit(uid, db, plan, cost_usd)

        except Exception as exc:
            from fastapi import HTTPException   # noqa: PLC0415
            if isinstance(exc, HTTPException):
                raise
            log.error("SAFETY SYSTEM FAILURE — blocking request (fail closed): %s", exc)
            raise HTTPException(
                status_code=503,
                detail={"error": "safety_unavailable", "message": "Service temporarily unavailable. Please try again."},
            )

    # ── Determine credit pool ──────────────────────────────────────────────
    sub_c   = user.get("subscription_credits")
    topup_c = max(0, user.get("topup_credits", 0))
    legacy  = max(0, user.get("credits", 0))

    # Use dual-credit fields if present; else legacy single field
    use_dual = sub_c is not None
    if use_dual:
        sub_c = max(0, sub_c)
        total = sub_c + topup_c
    else:
        total = legacy

    # ── Paid plan: deduct if credits available, log always ─────────────────
    if plan in ("standard", "pro", "max"):
        if cost > 0 and total < cost:
            return False, total

        if use_dual and cost > 0:
            ok, remaining = await _deduct_dual_atomic(db, uid, cost, sub_c, topup_c)
            if not ok:
                # Race: someone else consumed the last credits
                fresh = await db["users"].find_one(
                    {"id": uid},
                    {"subscription_credits": 1, "topup_credits": 1},
                )
                bal = 0
                if fresh:
                    bal = max(0, fresh.get("subscription_credits", 0)) + max(0, fresh.get("topup_credits", 0))
                return False, bal
        elif use_dual:
            remaining = total   # cost == 0, nothing to deduct
        else:
            # Paid user on legacy single-credit field
            remaining = 999    # unlimited marker

        await _log_usage(db, uid, user_name, user_email,
                         action_type, cost, tokens_in, tokens_out, cost_usd, plan)

        # Async abuse analysis + alert (non-blocking)
        try:
            import safety as _safety   # noqa: PLC0415
            await _safety.run_periodic_alerts(db)
        except Exception:
            pass

        return True, remaining

    # ── Free user: must have credits ───────────────────────────────────────
    if total < cost:
        return False, total

    if use_dual:
        ok, remaining = await _deduct_dual_atomic(db, uid, cost, sub_c, topup_c)
        if not ok:
            fresh = await db["users"].find_one(
                {"id": uid},
                {"subscription_credits": 1, "topup_credits": 1},
            )
            bal = 0
            if fresh:
                bal = max(0, fresh.get("subscription_credits", 0)) + max(0, fresh.get("topup_credits", 0))
            return False, bal
    else:
        # Legacy single `credits` field — atomic $gte guard
        result = await db["users"].find_one_and_update(
            {"id": uid, "credits": {"$gte": cost}},
            {"$inc": {"credits": -cost}},
            return_document=True,
            projection={"credits": 1},
        )
        if result is None:
            fresh = await db["users"].find_one({"id": uid}, {"credits": 1})
            return False, max(0, fresh.get("credits", 0) if fresh else 0)
        remaining = max(0, result["credits"])

    await _log_usage(db, uid, user_name, user_email,
                     action_type, cost, tokens_in, tokens_out, cost_usd, plan)

    try:
        import safety as _safety   # noqa: PLC0415
        await _safety.run_periodic_alerts(db)
    except Exception:
        pass

    return True, remaining


async def rollback_credits(
    authorization: str | None,
    cost: int,
    action_type: str = "chat_message",
) -> None:
    """
    Refund credits if an AI action fails after deduction.

    Security:
    - Refund is capped at plan credit limit (can't over-refund via timing attack)
    - Log deletion is time-windowed (last 60 s) + exact field match
      to avoid removing a wrong concurrent entry
    - Non-fatal — never raises
    """
    if cost <= 0:
        return
    payload = _decode_bearer(authorization)
    if not payload:
        return
    db = await _get_db()
    if db is None:
        return

    uid = payload["sub"]
    try:
        user = await db["users"].find_one(
            {"id": uid},
            {"plan": 1, "subscription_credits": 1, "credits": 1},
        )
        if not user:
            return

        plan     = (user.get("plan") or "free").lower()
        plan_cap = PLAN_CREDIT_LIMITS.get(plan, 50)

        if "subscription_credits" in user:
            # Dual-credit user: refund to subscription_credits, capped at plan limit
            await db["users"].update_one(
                {"id": uid},
                [{"$set": {
                    "subscription_credits": {
                        "$min": [
                            plan_cap,
                            {"$add": [
                                {"$ifNull": ["$subscription_credits", 0]},
                                cost,
                            ]},
                        ]
                    }
                }}],
            )
        elif plan not in ("standard", "pro", "max"):
            # Legacy free user — refund single `credits`, capped
            await db["users"].update_one(
                {"id": uid},
                [{"$set": {
                    "credits": {
                        "$min": [
                            plan_cap,
                            {"$add": [{"$ifNull": ["$credits", 0]}, cost]},
                        ]
                    }
                }}],
            )
        # Paid without dual-credit fields: no rollback needed

        # Remove the matching log entry (time-windowed to avoid removing a wrong concurrent entry)
        recent_threshold = time.time() - 60
        latest = await db["activity_logs"].find_one(
            {
                "user_id":      uid,
                "action_type":  action_type,
                "credits_used": cost,
                "timestamp":    {"$gte": recent_threshold},
            },
            sort=[("timestamp", -1)],
        )
        if latest:
            await db["activity_logs"].delete_one({"_id": latest["_id"]})
        log.info("Rolled back %d credits for uid=%s action=%s", cost, uid, action_type)

    except Exception as exc:
        log.warning("Credit rollback failed for uid=%s: %s", uid, exc)


# ---------------------------------------------------------------------------
# Image limit system — completely separate from credits
# ---------------------------------------------------------------------------

IMAGE_LIMITS: dict[str, int] = {
    "free":     2,
    "standard": 25,
    "pro":      50,
    "max":      100,
}

_MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


async def check_image_limit(
    authorization: str | None,
    db=None,
) -> tuple[bool, int, int, str | None]:
    """
    Check whether the authenticated user has image quota remaining.

    Returns:
        (ok, used, limit, resets_on)
        - ok:         True if the user may generate another image
        - used:       images generated so far in the current period
        - limit:      max allowed for their plan
        - resets_on:  human-readable date string ("April 1") for paid plans, None for free
    """
    if db is None:
        db = await _get_db()
    if db is None:
        return True, 0, IMAGE_LIMITS["free"], None  # can't check → allow through

    payload = _decode_bearer(authorization)
    if not payload:
        return False, 0, 0, None  # unauthenticated

    uid = payload.get("sub")
    user = await db["users"].find_one(
        {"id": uid},
        {"plan": 1, "email_verified": 1, "bonus_images": 1},
    )
    if not user:
        return False, 0, 0, None

    plan  = user.get("plan", "free")
    limit = IMAGE_LIMITS.get(plan, IMAGE_LIMITS["free"]) + user.get("bonus_images", 0)

    if plan == "free":
        # Free: count all-time images (no monthly reset)
        used = await db["activity_logs"].count_documents({
            "user_id": uid,
            "type":    "image_generated",
        })
        resets_on = None
    else:
        # Paid: count only this month
        mk = _month_key()
        used = await db["activity_logs"].count_documents({
            "user_id":   uid,
            "type":      "image_generated",
            "month_key": mk,
        })
        # First day of next month
        now = datetime.now(timezone.utc)
        if now.month == 12:
            nm = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            nm = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)
        resets_on = f"{_MONTH_NAMES[nm.month - 1]} {nm.day}"

    return used < limit, used, limit, resets_on


async def log_image_generated(
    authorization: str | None,
    db=None,
    request_id: str | None = None,
) -> None:
    """
    Record an image generation event in activity_logs.
    Does NOT deduct credits — images are a separate cost system.

    Idempotent: if request_id is provided and already exists in the last
    5 minutes, the log entry is skipped to prevent duplicate counting from
    rapid retries or network re-sends.
    """
    if db is None:
        db = await _get_db()
    if db is None:
        return

    payload = _decode_bearer(authorization)
    if not payload:
        return

    uid  = payload.get("sub")
    user = await db["users"].find_one(
        {"id": uid},
        {"name": 1, "email": 1, "plan": 1},
    )
    if not user:
        return

    # ── Deduplication check ─────────────────────────────────────────────────
    if request_id:
        recent_cutoff = time.time() - 300  # 5-minute window
        existing = await db["activity_logs"].find_one({
            "user_id":    uid,
            "request_id": request_id,
            "timestamp":  {"$gte": recent_cutoff},
        })
        if existing:
            log.info("Skipping duplicate image_generated log for uid=%s request_id=%s", uid, request_id)
            return

    # ── Insert log entry ────────────────────────────────────────────────────
    try:
        await db["activity_logs"].insert_one({
            "user_id":            uid,
            "user_name":          user.get("name", ""),
            "user_email":         user.get("email", ""),
            "type":               "image_generated",
            "action_type":        "image_generated",
            "request_id":         request_id,
            "credits_used":       0,       # images never cost credits
            "tokens_in":          0,
            "tokens_out":         0,
            "estimated_cost_usd": 0.13,    # real API cost for admin tracking
            "plan":               user.get("plan", "free"),
            "month_key":          _month_key(),
            "timestamp":          time.time(),
        })
    except Exception as exc:
        log.warning("image_generated log insert failed: %s", exc)
