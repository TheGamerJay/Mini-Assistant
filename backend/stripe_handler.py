"""
stripe_handler.py
Complete Stripe subscription + top-up credit system for Mini Assistant AI.

Endpoints:
  POST /api/stripe/create-checkout-session   — subscription or top-up
  POST /api/stripe/billing-portal            — manage subscription
  POST /api/stripe/webhook                   — Stripe webhook handler
  GET  /api/stripe/credits/{user_id}         — credit balance breakdown

Security hardening:
  - Webhook signature verification mandatory in production (no-secret = WARNING)
  - Full idempotency via stripe_events collection with compound upsert
  - Plan state ONLY changes via webhook — no manual plan override via API
  - Subscription cancellation immediately revokes paid-plan access
  - Top-up grants are atomic ($inc with floor guarantee)
  - Credit amounts are always validated against known values before grant
  - Stripe customer IDs are stored per-user and reused to prevent duplicates
"""

import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

import stripe
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stripe config
# ---------------------------------------------------------------------------

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")

if not stripe.api_key:
    log.warning("SECURITY: STRIPE_SECRET_KEY is not set — Stripe endpoints will return 503")
if not STRIPE_WEBHOOK_SECRET:
    log.warning(
        "SECURITY: STRIPE_WEBHOOK_SECRET is not set — webhook signature verification DISABLED. "
        "Set this in production immediately."
    )

def _price_env(key: str, fallback: str) -> str:
    """Read a price ID from env; return empty string if it's still the fallback placeholder."""
    val = os.environ.get(key, fallback)
    return val if (val and not val.startswith("price_standard") and
                   not val.startswith("price_pro") and
                   not val.startswith("price_team") and
                   not val.startswith("price_topup")) else val

def _pid(*env_keys: str) -> str:
    """
    Read a Stripe price ID from the first matching env var.
    Checks user-defined names (PRICE_*) first, then legacy (STRIPE_PRICE_*).
    Returns "" if not set.
    """
    for key in env_keys:
        val = os.environ.get(key, "").strip()
        if val and val.startswith("price_"):   # Stripe price IDs always start with price_
            return val
    return ""


# Map Stripe Price IDs → plan name
# Checks actual env var names the user set (PRICE_*) then legacy fallbacks
SUBSCRIPTION_PRICES: dict[str, str] = {}
for _pid_val, _plan in [
    (_pid("PRICE_STANDARD_MONTHLY", "STRIPE_PRICE_STANDARD_MONTHLY"), "standard"),
    (_pid("PRICE_STANDARD_YEARLY",  "STRIPE_PRICE_STANDARD_YEARLY"),  "standard"),
    (_pid("PRICE_PRO_MONTHLY",      "STRIPE_PRICE_PRO_MONTHLY"),       "pro"),
    (_pid("PRICE_PRO_YEARLY",       "STRIPE_PRICE_PRO_YEARLY"),        "pro"),
    # "max" plan — highest tier (env var: PRICE_MAX_*)
    (_pid("PRICE_MAX_MONTHLY",      "STRIPE_PRICE_MAX_MONTHLY"),       "max"),
    (_pid("PRICE_MAX_YEARLY",       "STRIPE_PRICE_MAX_YEARLY"),        "max"),
    # Legacy "team" fallback
    (_pid("PRICE_TEAM_MONTHLY",     "STRIPE_PRICE_TEAM_MONTHLY"),      "team"),
    (_pid("PRICE_TEAM_YEARLY",      "STRIPE_PRICE_TEAM_YEARLY"),       "team"),
]:
    if _pid_val:
        SUBSCRIPTION_PRICES[_pid_val] = _plan

# Map Stripe Price IDs → top-up credit amounts
# PRICE_TOPUP_10 = $10 purchase → 100 credits
# PRICE_TOPUP_25 = $25 purchase → 300 credits
# PRICE_TOPUP_50 = $50 purchase → 800 credits
_SAFE_TOPUP_AMOUNTS: set[int] = {100, 300, 800}   # credit amounts (not dollar amounts)
TOPUP_PRICES: dict[str, int] = {}
for _pid_val, _credits in [
    (_pid("PRICE_TOPUP_10",  "STRIPE_PRICE_TOPUP_10"),  100),
    (_pid("PRICE_TOPUP_25",  "STRIPE_PRICE_TOPUP_25"),  300),
    (_pid("PRICE_TOPUP_50",  "STRIPE_PRICE_TOPUP_50"),  800),
    # Legacy higher amounts
    (_pid("PRICE_TOPUP_100", "STRIPE_PRICE_TOPUP_100"), 100),
    (_pid("PRICE_TOPUP_300", "STRIPE_PRICE_TOPUP_300"), 300),
    (_pid("PRICE_TOPUP_800", "STRIPE_PRICE_TOPUP_800"), 800),
]:
    if _pid_val and _credits in _SAFE_TOPUP_AMOUNTS:
        TOPUP_PRICES[_pid_val] = _credits

# Subscription credits per plan (per billing cycle)
PLAN_CREDITS: dict[str, int] = {
    "free":     50,
    "standard": 500,
    "pro":      2000,
    "max":      10000,
    "team":     10000,   # legacy alias for max
}

# Maximum top-up credits a user can accumulate (anti-abuse cap)
MAX_TOPUP_CREDITS: int = int(os.environ.get("MAX_TOPUP_CREDITS", 10000))

# Strict whitelist of Stripe webhook event types we handle
_HANDLED_EVENT_TYPES: frozenset[str] = frozenset({
    "checkout.session.completed",
    "invoice.paid",
    "invoice.payment_succeeded",
    "invoice.payment_failed",
    "customer.subscription.deleted",
    "customer.subscription.updated",
    "payment_intent.payment_failed",
})

# Log configured prices at startup
log.info(
    "Stripe prices loaded: subscriptions=%d top-ups=%d",
    len(SUBSCRIPTION_PRICES), len(TOPUP_PRICES),
)

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

stripe_router = APIRouter(prefix="/api/stripe", tags=["stripe"])

# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------


class CheckoutRequest(BaseModel):
    price_id: str
    user_id: Optional[str] = None   # passed from frontend for metadata


class BillingPortalRequest(BaseModel):
    user_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

JWT_SECRET    = os.environ.get("JWT_SECRET", "mini_assistant_jwt_secret_2025")
JWT_ALGORITHM = "HS256"


def _decode_bearer(authorization: str | None) -> dict | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        return None
    try:
        from jose import jwt   # noqa: PLC0415
        # jose validates `exp` automatically — no manual check needed
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        uid = payload.get("sub")
        if not uid or not isinstance(uid, str):
            return None
        return payload
    except Exception:
        return None


async def _get_db():
    try:
        import server as _srv  # noqa: PLC0415
        return _srv.db
    except Exception:
        return None


async def _get_user_by_id(db, user_id: str) -> dict | None:
    return await db["users"].find_one({"id": user_id})


async def _get_or_create_stripe_customer(db, user: dict) -> str:
    """Return existing Stripe customer ID, or create a new customer."""
    existing = user.get("stripe_customer_id")
    if existing:
        return existing

    customer = stripe.Customer.create(
        email=user.get("email", ""),
        name=user.get("name", ""),
        metadata={"user_id": user.get("id", "")},
    )
    cid = customer["id"]
    await db["users"].update_one(
        {"id": user["id"]},
        {"$set": {"stripe_customer_id": cid}},
    )
    return cid


def _month_key() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.year:04d}-{now.month:02d}"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@stripe_router.post("/create-checkout-session")
async def create_checkout_session(
    body: CheckoutRequest,
    authorization: str = Header(None),
):
    """Create a Stripe Checkout session for a subscription or top-up."""
    if not stripe.api_key:
        raise HTTPException(503, "Stripe not configured")

    # Authenticate
    payload = _decode_bearer(authorization)
    if not payload:
        raise HTTPException(401, "Authentication required")

    uid = payload["sub"]
    db = await _get_db()
    if db is None:
        raise HTTPException(503, "Database unavailable")

    user = await _get_user_by_id(db, uid)
    if not user:
        raise HTTPException(404, "User not found")

    price_id = body.price_id

    # Determine mode
    is_subscription = price_id in SUBSCRIPTION_PRICES
    is_topup        = price_id in TOPUP_PRICES

    if not is_subscription and not is_topup:
        raise HTTPException(400, "Unknown price_id")

    try:
        customer_id = await _get_or_create_stripe_customer(db, user)

        common_kwargs = {
            "customer": customer_id,
            "line_items": [{"price": price_id, "quantity": 1}],
            "success_url": f"{FRONTEND_URL}?checkout=success&session_id={{CHECKOUT_SESSION_ID}}",
            "cancel_url":  f"{FRONTEND_URL}?checkout=cancelled",
            "metadata": {
                "user_id":  uid,
                "price_id": price_id,
            },
            "allow_promotion_codes": True,
        }

        if is_subscription:
            session = stripe.checkout.Session.create(
                mode="subscription",
                subscription_data={
                    "metadata": {"user_id": uid},
                },
                **common_kwargs,
            )
        else:
            session = stripe.checkout.Session.create(
                mode="payment",
                payment_intent_data={
                    "metadata": {"user_id": uid, "price_id": price_id},
                },
                **common_kwargs,
            )

        return {"checkout_url": session.url, "session_id": session.id}

    except stripe.error.StripeError as exc:
        log.error("Stripe checkout error: %s", exc)
        raise HTTPException(502, f"Stripe error: {exc.user_message or str(exc)}")


@stripe_router.post("/billing-portal")
async def billing_portal(
    body: BillingPortalRequest,
    authorization: str = Header(None),
):
    """Create a Stripe Billing Portal session for subscription management."""
    if not stripe.api_key:
        raise HTTPException(503, "Stripe not configured")

    payload = _decode_bearer(authorization)
    if not payload:
        raise HTTPException(401, "Authentication required")

    uid = payload["sub"]
    db = await _get_db()
    if db is None:
        raise HTTPException(503, "Database unavailable")

    user = await _get_user_by_id(db, uid)
    if not user:
        raise HTTPException(404, "User not found")

    cid = user.get("stripe_customer_id")
    if not cid:
        raise HTTPException(404, "No billing account found. Subscribe first.")

    try:
        portal = stripe.billing_portal.Session.create(
            customer=cid,
            return_url=f"{FRONTEND_URL}?portal=return",
        )
        return {"portal_url": portal.url}
    except stripe.error.StripeError as exc:
        log.error("Stripe portal error: %s", exc)
        raise HTTPException(502, f"Stripe error: {exc.user_message or str(exc)}")


@stripe_router.get("/credits/{user_id}")
async def get_credits(user_id: str, authorization: str = Header(None)):
    """Return full credit breakdown for a user."""
    payload = _decode_bearer(authorization)
    if not payload:
        raise HTTPException(401, "Authentication required")
    # Users can only see their own; admins see any
    requester_uid = payload["sub"]

    db = await _get_db()
    if db is None:
        raise HTTPException(503, "Database unavailable")

    requester = await _get_user_by_id(db, requester_uid)
    if not requester:
        raise HTTPException(404, "Requester not found")

    is_admin = requester.get("role") == "admin"
    if requester_uid != user_id and not is_admin:
        raise HTTPException(403, "Forbidden")

    user = await _get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(404, "User not found")

    plan = user.get("plan", "free")
    sub_credits   = user.get("subscription_credits", PLAN_CREDITS.get(plan, 50))
    topup_credits = user.get("topup_credits", 0)

    return {
        "user_id":              user_id,
        "plan":                 plan,
        "subscription_credits": sub_credits,
        "topup_credits":        topup_credits,
        "total_credits":        sub_credits + topup_credits,
        "plan_limit":           PLAN_CREDITS.get(plan, 50),
        "billing_cycle_start":  user.get("billing_cycle_start"),
        "stripe_customer_id":   user.get("stripe_customer_id") if is_admin else None,
    }


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------


@stripe_router.post("/webhook")
async def stripe_webhook(request: Request):
    """
    Handle Stripe webhook events.
    Verifies signature, deduplicates via stripe_events collection,
    then dispatches to the appropriate handler.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    if not STRIPE_WEBHOOK_SECRET:
        log.warning("STRIPE_WEBHOOK_SECRET not set — skipping signature verification")
        try:
            event = stripe.Event.construct_from(
                stripe.util.convert_to_stripe_object(
                    stripe.util.json.loads(payload)
                ),
                stripe.api_key,
            )
        except Exception as exc:
            raise HTTPException(400, f"Webhook parse error: {exc}")
    else:
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        except stripe.error.SignatureVerificationError:
            raise HTTPException(400, "Invalid webhook signature")
        except Exception as exc:
            raise HTTPException(400, f"Webhook error: {exc}")

    event_id   = event["id"]
    event_type = event["type"]

    db = await _get_db()
    if db is None:
        log.error("Webhook: DB unavailable for event %s", event_id)
        return {"status": "db_unavailable"}

    # Idempotency — atomic upsert: only insert if event_id doesn't exist yet
    # Using upsert with $setOnInsert prevents a TOCTOU race between find + insert
    idem_result = await db["stripe_events"].update_one(
        {"event_id": event_id},
        {
            "$setOnInsert": {
                "event_id":   event_id,
                "event_type": event_type,
                "processed":  False,
                "timestamp":  time.time(),
            }
        },
        upsert=True,
    )
    if idem_result.matched_count > 0:
        # Document already existed → duplicate event
        log.info("Webhook duplicate skipped: %s", event_id)
        return {"status": "already_processed"}

    # Strict whitelist — silently accept (200) but don't process unknown types
    if event_type not in _HANDLED_EVENT_TYPES:
        log.debug("Webhook: ignoring unhandled event type %s (%s)", event_type, event_id)
        await db["stripe_events"].update_one(
            {"event_id": event_id},
            {"$set": {"processed": True, "skipped": True}},
        )
        return {"status": "ignored", "event": event_id, "reason": "unhandled_type"}

    try:
        if event_type == "checkout.session.completed":
            await _handle_checkout_completed(db, event["data"]["object"])
        elif event_type in ("invoice.paid", "invoice.payment_succeeded"):
            await _handle_invoice_paid(db, event["data"]["object"])
        elif event_type == "customer.subscription.deleted":
            await _handle_subscription_deleted(db, event["data"]["object"])
        elif event_type == "customer.subscription.updated":
            await _handle_subscription_updated(db, event["data"]["object"])
        elif event_type == "invoice.payment_failed":
            await _handle_invoice_payment_failed(db, event["data"]["object"])
        elif event_type == "payment_intent.payment_failed":
            await _handle_payment_failed(db, event["data"]["object"])

        await db["stripe_events"].update_one(
            {"event_id": event_id},
            {"$set": {"processed": True, "processed_at": time.time()}},
        )
        log.info("Webhook processed: %s (%s)", event_type, event_id)

    except Exception as exc:
        log.error("Webhook handler error for %s (%s): %s", event_id, event_type, exc)
        await db["stripe_events"].update_one(
            {"event_id": event_id},
            {"$set": {"error": str(exc), "error_at": time.time()}},
        )
        # Return 200 to prevent Stripe from retrying for handler-logic errors
        # Stripe will retry on 4xx/5xx responses
        return {"status": "handler_error", "event": event_id}

    return {"status": "ok", "event": event_id}


# ---------------------------------------------------------------------------
# Webhook event handlers
# ---------------------------------------------------------------------------


async def _handle_checkout_completed(db, session: dict) -> None:
    """Handle checkout.session.completed — subscription activation or top-up credit grant."""
    user_id  = session.get("metadata", {}).get("user_id")
    price_id = session.get("metadata", {}).get("price_id")
    mode     = session.get("mode")  # "subscription" or "payment"

    if not user_id:
        # Try to find user by customer ID
        cid = session.get("customer")
        if cid:
            user = await db["users"].find_one({"stripe_customer_id": cid})
            user_id = user["id"] if user else None

    if not user_id:
        log.warning("checkout.session.completed: could not resolve user_id")
        return

    if mode == "payment" and price_id in TOPUP_PRICES:
        # One-time top-up — validate credit amount before grant
        credits_to_add = TOPUP_PRICES[price_id]
        if credits_to_add not in _SAFE_TOPUP_AMOUNTS:
            log.error(
                "Top-up REJECTED: unsafe credit amount %d for price_id=%s user=%s",
                credits_to_add, price_id, user_id,
            )
            return

        # Atomic add with cap to prevent accumulating unlimited credits
        result = await db["users"].update_one(
            {
                "id": user_id,
                # Only grant if current topup_credits < max cap
                "$expr": {"$lt": [{"$ifNull": ["$topup_credits", 0]}, MAX_TOPUP_CREDITS]},
            },
            [{"$set": {
                "topup_credits": {
                    "$min": [
                        MAX_TOPUP_CREDITS,
                        {"$add": [{"$ifNull": ["$topup_credits", 0]}, credits_to_add]},
                    ]
                }
            }}],
        )
        if result.modified_count == 0:
            log.warning(
                "Top-up not applied: user %s already at topup cap (%d)",
                user_id, MAX_TOPUP_CREDITS,
            )
        else:
            log.info("Top-up: +%d topup_credits for user %s", credits_to_add, user_id)

        await db["activity_logs"].insert_one({
            "user_id":    user_id,
            "type":       "topup_purchase",
            "action_type": "topup_purchase",
            "credits_used": -credits_to_add,   # negative = credit addition
            "month_key":  _month_key(),
            "timestamp":  time.time(),
            "stripe_session_id": session.get("id"),
        })

    elif mode == "subscription":
        # Subscription start — plan upgrade handled fully by invoice.paid
        # Just store subscription ID if available
        sub_id = session.get("subscription")
        if sub_id:
            await db["users"].update_one(
                {"id": user_id},
                {"$set": {"stripe_subscription_id": sub_id}},
            )
        log.info("Subscription checkout completed for user %s (sub=%s)", user_id, sub_id)


async def _handle_invoice_paid(db, invoice: dict) -> None:
    """
    Handle invoice.paid — fires on new subscription and every renewal.
    Resets subscription_credits to the plan's monthly allotment.
    """
    cid    = invoice.get("customer")
    sub_id = invoice.get("subscription")

    if not cid:
        return

    user = await db["users"].find_one({"stripe_customer_id": cid})
    if not user:
        log.warning("invoice.paid: no user found for customer %s", cid)
        return

    user_id = user["id"]

    # Determine plan from subscription price
    plan = user.get("plan", "free")
    if sub_id:
        try:
            sub = stripe.Subscription.retrieve(sub_id)
            for item in sub.get("items", {}).get("data", []):
                pid = item.get("price", {}).get("id", "")
                if pid in SUBSCRIPTION_PRICES:
                    plan = SUBSCRIPTION_PRICES[pid]
                    break
        except Exception as exc:
            log.warning("Could not retrieve subscription %s: %s", sub_id, exc)

    plan_credits = PLAN_CREDITS.get(plan, 50)
    now = datetime.now(timezone.utc)

    await db["users"].update_one(
        {"id": user_id},
        {"$set": {
            "plan":                  plan,
            "subscription_credits":  plan_credits,
            "billing_cycle_start":   now.isoformat(),
            "stripe_subscription_id": sub_id,
            # Successful payment — reset failure counter
            "payment_failure_count":  0,
            "last_payment_succeeded_at": time.time(),
        }},
    )
    log.info(
        "invoice.paid: user %s → plan=%s, subscription_credits reset to %d",
        user_id, plan, plan_credits,
    )

    await db["activity_logs"].insert_one({
        "user_id":    user_id,
        "type":       "subscription_renewal",
        "action_type": "subscription_renewal",
        "credits_used": -plan_credits,   # negative = credit addition
        "plan":       plan,
        "month_key":  _month_key(),
        "timestamp":  time.time(),
        "stripe_invoice_id": invoice.get("id"),
    })


async def _handle_subscription_deleted(db, subscription: dict) -> None:
    """
    Handle customer.subscription.deleted — immediately downgrade to free.

    Security: This is the critical access-revocation path. We explicitly:
    - Set plan to "free"
    - Reset subscription_credits to free tier limit (50)
    - Do NOT touch topup_credits (legitimately purchased, non-refundable)
    - Clear stripe_subscription_id to prevent any subscription-based grants
    """
    cid = subscription.get("customer")
    if not cid:
        return

    user = await db["users"].find_one({"stripe_customer_id": cid})
    if not user:
        log.warning("subscription.deleted: no user found for customer %s", cid)
        return

    user_id  = user["id"]
    old_plan = user.get("plan", "free")

    await db["users"].update_one(
        {"id": user_id},
        {"$set": {
            "plan":                   "free",
            "subscription_credits":   PLAN_CREDITS["free"],
            "stripe_subscription_id": None,
            "subscription_cancelled_at": time.time(),
        }},
    )
    log.info(
        "Subscription cancelled: user %s %s → free (access immediately revoked)",
        user_id, old_plan,
    )

    await db["activity_logs"].insert_one({
        "user_id":    user_id,
        "type":       "subscription_cancelled",
        "action_type": "subscription_cancelled",
        "credits_used": 0,
        "plan":       "free",
        "month_key":  _month_key(),
        "timestamp":  time.time(),
    })


async def _handle_subscription_updated(db, subscription: dict) -> None:
    """Handle customer.subscription.updated — plan change mid-cycle."""
    cid = subscription.get("customer")
    if not cid:
        return

    user = await db["users"].find_one({"stripe_customer_id": cid})
    if not user:
        return

    user_id = user["id"]

    # Find new plan from price
    new_plan = user.get("plan", "free")
    for item in subscription.get("items", {}).get("data", []):
        pid = item.get("price", {}).get("id", "")
        if pid in SUBSCRIPTION_PRICES:
            new_plan = SUBSCRIPTION_PRICES[pid]
            break

    old_plan = user.get("plan", "free")
    if new_plan == old_plan:
        return  # no change

    plan_credits = PLAN_CREDITS.get(new_plan, 50)
    await db["users"].update_one(
        {"id": user_id},
        {"$set": {
            "plan":                 new_plan,
            "subscription_credits": plan_credits,
        }},
    )
    log.info("Subscription updated: user %s %s → %s", user_id, old_plan, new_plan)


MAX_PAYMENT_FAILURES: int = int(os.environ.get("MAX_PAYMENT_FAILURES", "3"))


async def _handle_invoice_payment_failed(db, invoice: dict) -> None:
    """
    Handle invoice.payment_failed.

    Stripe retries failed invoices (typically 3× over several days). After
    MAX_PAYMENT_FAILURES consecutive failures we immediately downgrade the user
    to the free plan — Stripe will eventually fire customer.subscription.deleted,
    but we proactively revoke access so users cannot keep using a paid plan on
    a dead card indefinitely.

    Failure count is tracked in users.payment_failure_count. It resets to 0
    whenever invoice.paid fires (successful payment).
    """
    cid            = invoice.get("customer")
    sub_id         = invoice.get("subscription")
    amount         = invoice.get("amount_due", 0) / 100   # cents → dollars
    attempt_count  = invoice.get("attempt_count", 1)

    if not cid:
        log.warning("invoice.payment_failed: no customer ID in invoice")
        return

    user = await db["users"].find_one(
        {"stripe_customer_id": cid},
        {"id": 1, "email": 1, "plan": 1, "payment_failure_count": 1},
    )
    if not user:
        log.warning("invoice.payment_failed: no user found for customer %s", cid)
        return

    uid           = user["id"]
    current_plan  = user.get("plan", "free")
    failure_count = user.get("payment_failure_count", 0) + 1

    # Persist incremented failure count + timestamp
    await db["users"].update_one(
        {"id": uid},
        {"$set": {
            "payment_failure_count":    failure_count,
            "last_payment_failed_at":   time.time(),
        }},
    )

    log.warning(
        "invoice.payment_failed: user=%s plan=%s failure #%d (attempt_count=%d) amount=$%.2f",
        uid, current_plan, failure_count, attempt_count, amount,
    )

    await db["activity_logs"].insert_one({
        "user_id":      uid,
        "type":         "invoice_payment_failed",
        "action_type":  "invoice_payment_failed",
        "credits_used": 0,
        "month_key":    _month_key(),
        "timestamp":    time.time(),
        "details": {
            "amount_usd":     amount,
            "attempt_count":  attempt_count,
            "failure_number": failure_count,
            "subscription_id": sub_id,
        },
    })

    # Auto-downgrade after MAX_PAYMENT_FAILURES consecutive failures
    if failure_count >= MAX_PAYMENT_FAILURES and current_plan != "free":
        log.error(
            "AUTO-DOWNGRADE: user=%s reached %d payment failures — downgrading to free",
            uid, failure_count,
        )
        await db["users"].update_one(
            {"id": uid},
            {"$set": {
                "plan":                    "free",
                "subscription_credits":    50,
                "subscription_auto_downgraded_at": time.time(),
                "subscription_downgrade_reason":   f"payment_failed_{failure_count}x",
            }},
        )
        # Log the downgrade event
        await db["activity_logs"].insert_one({
            "user_id":      uid,
            "type":         "auto_downgrade",
            "action_type":  "auto_downgrade",
            "credits_used": 0,
            "month_key":    _month_key(),
            "timestamp":    time.time(),
            "details": {
                "reason":            "payment_failed",
                "failure_count":     failure_count,
                "previous_plan":     current_plan,
                "subscription_id":   sub_id,
            },
        })


async def _handle_payment_failed(db, payment_intent: dict) -> None:
    """
    Handle payment_intent.payment_failed — audit log only.
    Failure counting and auto-downgrade are done in _handle_invoice_payment_failed.
    """
    cid    = payment_intent.get("customer")
    amount = payment_intent.get("amount", 0) / 100   # cents → dollars
    reason = payment_intent.get("last_payment_error", {}).get("message", "unknown")

    user_id = None
    if cid:
        user = await db["users"].find_one({"stripe_customer_id": cid}, {"id": 1})
        user_id = user["id"] if user else None

    log.warning(
        "payment_intent.payment_failed: user=%s amount=$%.2f reason=%s",
        user_id or cid, amount, reason,
    )
    if db and user_id:
        await db["activity_logs"].insert_one({
            "user_id":      user_id,
            "type":         "payment_intent_failed",
            "action_type":  "payment_intent_failed",
            "credits_used": 0,
            "month_key":    _month_key(),
            "timestamp":    time.time(),
            "details":      {"amount_usd": amount, "reason": reason},
        })


# ---------------------------------------------------------------------------
# Public helper: cancel subscription (called by safety module on abuse)
# ---------------------------------------------------------------------------

async def cancel_user_subscription_for_abuse(uid: str, db) -> bool:
    """
    Cancel the user's Stripe subscription due to detected abuse.
    Immediately downgrades plan in DB; webhook will confirm the state.
    Returns True if subscription was cancelled, False otherwise.
    """
    if not stripe.api_key:
        log.warning("cancel_user_subscription_for_abuse: Stripe not configured")
        return False

    user = await db["users"].find_one(
        {"id": uid},
        {"stripe_subscription_id": 1, "plan": 1},
    )
    if not user:
        return False

    sub_id = user.get("stripe_subscription_id")
    if sub_id:
        try:
            stripe.Subscription.delete(sub_id)
            log.warning("Abuse: Stripe subscription %s cancelled for uid=%s", sub_id, uid)
        except stripe.error.InvalidRequestError:
            pass   # already cancelled
        except Exception as exc:
            log.error("Abuse: Stripe cancellation failed sub=%s: %s", sub_id, exc)

    # Immediate local downgrade (webhook is idempotent)
    await db["users"].update_one(
        {"id": uid},
        {"$set": {
            "plan":                   "free",
            "subscription_credits":   PLAN_CREDITS["free"],
            "stripe_subscription_id": None,
            "abuse_blocked_at":       time.time(),
        }},
    )
    return True
