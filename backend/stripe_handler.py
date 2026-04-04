"""
stripe_handler.py
Stripe subscription management for Mini Assistant AI (BYOK model).

Endpoints:
  POST /api/stripe/create-checkout-session   — subscription only
  POST /api/stripe/billing-portal            — manage subscription
  POST /api/stripe/webhook                   — Stripe webhook handler
  GET  /api/stripe/prices                    — configured price IDs

Security hardening:
  - Webhook signature verification mandatory (no-secret = RuntimeError at startup)
  - Full idempotency via stripe_events collection with compound upsert
  - Subscription state ONLY changes via webhook — no manual override via API
  - Cancellation immediately revokes access (is_subscribed=False)
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
    raise RuntimeError(
        "STRIPE_WEBHOOK_SECRET environment variable is not set. "
        "Refusing to start — webhook signature verification would be disabled, "
        "allowing forged Stripe events."
    )

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


# ---------------------------------------------------------------------------
# Price ID registry — all map to is_subscribed=True (BYOK model, no tiers)
# ---------------------------------------------------------------------------

# Canonical price IDs — single plan, monthly/yearly only
PRICE_MONTHLY = _pid("PRICE_MONTHLY")
PRICE_YEARLY  = _pid("PRICE_YEARLY")

# Subscription price → interval label ("month" | "year")
# Only PRICE_MONTHLY and PRICE_YEARLY are active. Legacy price vars removed.
SUBSCRIPTION_PRICES: dict[str, str] = {}
for _pid_val, _interval in [
    (PRICE_MONTHLY, "month"),
    (PRICE_YEARLY,  "year"),
]:
    if _pid_val:
        SUBSCRIPTION_PRICES[_pid_val] = _interval

# Ad Mode add-on price IDs (independent of main subscription)
_AD_MODE_MONTHLY_ID = _pid("STRIPE_AD_MODE_MONTHLY")
_AD_MODE_YEARLY_ID  = _pid("STRIPE_AD_MODE_YEARLY")
AD_MODE_PRICES: frozenset[str] = frozenset(
    p for p in [_AD_MODE_MONTHLY_ID, _AD_MODE_YEARLY_ID] if p
)
log.info("Ad Mode prices loaded: %d", len(AD_MODE_PRICES))

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

log.info("Stripe prices loaded: subscriptions=%d", len(SUBSCRIPTION_PRICES))

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

    if price_id not in SUBSCRIPTION_PRICES:
        raise HTTPException(400, "Unknown price_id")

    try:
        customer_id = await _get_or_create_stripe_customer(db, user)

        session = stripe.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            line_items=[{"price": price_id, "quantity": 1}],
            subscription_data={"metadata": {"user_id": uid}},
            success_url=f"{FRONTEND_URL}/onboarding/api-key?checkout=success&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{FRONTEND_URL}?checkout=cancelled",
            metadata={"user_id": uid, "price_id": price_id},
            allow_promotion_codes=True,
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


@stripe_router.get("/prices")
async def get_prices():
    """Return configured Stripe price IDs for the frontend."""
    return {
        "monthly": PRICE_MONTHLY or None,
        "yearly":  PRICE_YEARLY  or None,
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
# Referral reward constants (must match auth_routes.py)
REFERRAL_DAYS_REFERRER  = 5    # subscription days added to referrer per reward
REFERRAL_DAYS_REFERRED  = 2    # days added to referred user's next billing cycle
REFERRAL_MAX_REWARDS    = 3    # max rewarded referrals
REFERRAL_MAX_REWARD_DAYS = 15  # referrer cap: 3 × 5 days


async def _process_referral_reward(db, subscribed_user: dict) -> None:
    """
    Called after a successful subscription payment.
    - Finds the referrer via referred_by code
    - Checks cap (referrals_rewarded_count < REFERRAL_MAX_REWARDS)
    - Ensures this referred user hasn't already triggered a reward
    - Awards days to referrer (subscription_end += days) and queues days for referred user
    """
    referred_by_code = subscribed_user.get("referred_by")
    if not referred_by_code:
        return

    if subscribed_user.get("referral_reward_given"):
        return

    referred_user_id = subscribed_user["id"]

    referrer = await db["users"].find_one({"referral_code": referred_by_code})
    if not referrer:
        return

    referrer_id = referrer["id"]

    if referrer_id == referred_user_id:
        log.warning("referral.reward: self-referral blocked user=%s", referred_user_id)
        return

    rewarded_count = referrer.get("referrals_rewarded_count", 0)
    if rewarded_count >= REFERRAL_MAX_REWARDS:
        log.info("referral.reward: referrer=%s hit cap (%d), no reward", referrer_id, REFERRAL_MAX_REWARDS)
        return

    # Atomic mark — prevent double reward
    res = await db["users"].update_one(
        {"id": referred_user_id, "referral_reward_given": {"$ne": True}},
        {"$set": {"referral_reward_given": True}},
    )
    if res.modified_count == 0:
        return  # race — already processed

    # Extend referrer's subscription_end by REFERRAL_DAYS_REFERRER
    referrer_end = referrer.get("subscription_end") or time.time()
    new_end = referrer_end + REFERRAL_DAYS_REFERRER * 86400
    await db["users"].update_one(
        {"id": referrer_id},
        {
            "$set": {"subscription_end": new_end},
            "$inc": {
                "referrals_rewarded_count": 1,
                "referrer_days_total":      REFERRAL_DAYS_REFERRER,
            },
        },
    )

    # Queue days for referred user — applied on their next invoice.paid
    await db["users"].update_one(
        {"id": referred_user_id},
        {"$inc": {"bonus_days_next_cycle": REFERRAL_DAYS_REFERRED}},
    )

    log.info(
        "referral.reward: referrer=%s +%d days (total=%d/%d) referred=%s +%d days next cycle",
        referrer_id, REFERRAL_DAYS_REFERRER, rewarded_count + 1, REFERRAL_MAX_REWARDS,
        referred_user_id, REFERRAL_DAYS_REFERRED,
    )

    now_ts = time.time()
    await db["activity_logs"].insert_many([
        {
            "user_id":          referrer_id,
            "type":             "referral_reward",
            "action_type":      "referral_reward",
            "referred_user_id": referred_user_id,
            "days_added":       REFERRAL_DAYS_REFERRER,
            "timestamp":        now_ts,
        },
        {
            "user_id":      referred_user_id,
            "type":         "referral_reward",
            "action_type":  "referral_reward",
            "referrer_id":  referrer_id,
            "days_queued":  REFERRAL_DAYS_REFERRED,
            "timestamp":    now_ts,
        },
    ])


# Webhook event handlers
# ---------------------------------------------------------------------------


async def _handle_checkout_completed(db, session: dict) -> None:
    """Handle checkout.session.completed — subscription activation."""
    user_id  = session.get("metadata", {}).get("user_id")
    price_id = session.get("metadata", {}).get("price_id")
    mode     = session.get("mode")

    if not user_id:
        cid = session.get("customer")
        if cid:
            user = await db["users"].find_one({"stripe_customer_id": cid})
            user_id = user["id"] if user else None

    if not user_id:
        log.warning("checkout.session.completed: could not resolve user_id")
        return

    if mode == "subscription":
        sub_id = session.get("subscription")
        if price_id and price_id in AD_MODE_PRICES:
            update: dict = {"has_ad_mode": True}
            if sub_id:
                update["ad_mode_subscription_id"] = sub_id
            await db["users"].update_one({"id": user_id}, {"$set": update})
            log.info("Ad Mode activated: user=%s sub=%s", user_id, sub_id)
        else:
            # Main subscription — full state set on invoice.paid
            if sub_id:
                await db["users"].update_one(
                    {"id": user_id},
                    {"$set": {"stripe_subscription_id": sub_id}},
                )
            log.info("Subscription checkout completed for user %s (sub=%s)", user_id, sub_id)


async def _handle_invoice_paid(db, invoice: dict) -> None:
    """
    Handle invoice.paid — fires on new subscription and every renewal.
    Sets is_subscribed=True, syncs subscription_end from Stripe period.
    Applies any queued bonus_days_next_cycle then resets the field.
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
    interval = "month"  # default; overridden below

    if sub_id:
        try:
            sub = stripe.Subscription.retrieve(sub_id)
            _sub_items = sub.get("items", {}).get("data", [])

            # Ad Mode renewal — don't touch main subscription
            _is_ad_mode = any(
                item.get("price", {}).get("id", "") in AD_MODE_PRICES
                for item in _sub_items
            )
            if _is_ad_mode:
                await db["users"].update_one(
                    {"id": user_id}, {"$set": {"has_ad_mode": True}}
                )
                log.info("invoice.paid: Ad Mode renewed for user=%s sub=%s", user_id, sub_id)
                return

            # Determine interval from price
            for item in _sub_items:
                pid = item.get("price", {}).get("id", "")
                if pid in SUBSCRIPTION_PRICES:
                    interval = SUBSCRIPTION_PRICES[pid]
                    break

            # Get Stripe's authoritative period end
            period_end = sub.get("current_period_end")
        except Exception as exc:
            log.warning("Could not retrieve subscription %s: %s", sub_id, exc)
            period_end = None
    else:
        period_end = None

    # Apply any queued referral bonus days on top of Stripe's period end
    bonus_days  = user.get("bonus_days_next_cycle", 0)
    base_end    = period_end or time.time()
    new_sub_end = base_end + (bonus_days * 86400 if bonus_days > 0 else 0)

    invoice_revenue = round((invoice.get("amount_paid") or 0) / 100, 2)

    update_set: dict = {
        "is_subscribed":              True,
        "subscription_interval":      interval,
        "subscription_end":           new_sub_end,
        "stripe_subscription_id":     sub_id,
        "payment_failure_count":      0,
        "last_payment_succeeded_at":  time.time(),
        "plan":                       "paid",
    }
    if bonus_days > 0:
        update_set["bonus_days_next_cycle"] = 0  # reset after applying

    inc_fields: dict = {
        "total_spend": invoice_revenue,
        **({"lifetime_value": invoice_revenue}
           if os.environ.get("LTV_TRACKING_ENABLED", "true").lower() == "true"
              and invoice_revenue > 0
           else {}),
    }

    await db["users"].update_one(
        {"id": user_id},
        {"$set": update_set, "$inc": inc_fields},
    )
    log.info(
        "invoice.paid: user=%s interval=%s sub_end=%s bonus_days=%d revenue=%.2f",
        user_id, interval, new_sub_end, bonus_days, invoice_revenue,
    )

    # ── Referral rewards (non-fatal) ────────────────────────────────────────
    try:
        await _process_referral_reward(db, user)
    except Exception as _ref_exc:
        log.warning("referral reward failed (non-fatal): %s", _ref_exc)

    # Send welcome / renewal email (non-fatal)
    try:
        from email_sender import send_welcome_email   # noqa: PLC0415
        from email_logger import mark_conversion      # noqa: PLC0415
        user_doc = await db["users"].find_one({"id": user_id}, {"email": 1, "name": 1})
        if user_doc and user_doc.get("email"):
            await send_welcome_email(
                to_email=user_doc["email"],
                to_name=user_doc.get("name", ""),
                plan="paid",
                credits=0,
                user_id=user_id,
                db=db,
            )
            await mark_conversion(db, user_id, "upgrade", window_hours=48, revenue=invoice_revenue)
    except Exception as _email_exc:
        log.warning("Welcome email failed (non-fatal): %s", _email_exc)

    await db["activity_logs"].insert_one({
        "user_id":           user_id,
        "type":              "subscription_renewal",
        "action_type":       "subscription_renewal",
        "interval":          interval,
        "month_key":         _month_key(),
        "timestamp":         time.time(),
        "stripe_invoice_id": invoice.get("id"),
    })


async def _handle_subscription_deleted(db, subscription: dict) -> None:
    """
    Handle customer.subscription.deleted — immediately revoke access.

    Security: This is the critical access-revocation path. We set
    is_subscribed=False which blocks all execution via access_gate.can_execute().
    """
    cid = subscription.get("customer")
    if not cid:
        return

    user = await db["users"].find_one({"stripe_customer_id": cid})
    if not user:
        log.warning("subscription.deleted: no user found for customer %s", cid)
        return

    user_id = user["id"]

    # Ad Mode cancellation — don't touch main subscription
    _sub_items = subscription.get("items", {}).get("data", [])
    _is_ad_mode = any(
        item.get("price", {}).get("id", "") in AD_MODE_PRICES
        for item in _sub_items
    )
    if _is_ad_mode:
        await db["users"].update_one(
            {"stripe_customer_id": cid},
            {"$set": {"has_ad_mode": False, "ad_mode_subscription_id": None}},
        )
        log.info("Ad Mode cancelled: user=%s", user_id)
        await db["activity_logs"].insert_one({
            "user_id":    user_id,
            "type":       "ad_mode_cancelled",
            "action_type": "ad_mode_cancelled",
            "month_key":  _month_key(),
            "timestamp":  time.time(),
        })
        return

    await db["users"].update_one(
        {"id": user_id},
        {"$set": {
            "is_subscribed":            False,
            "plan":                     "free",
            "stripe_subscription_id":   None,
            "subscription_cancelled_at": time.time(),
        }},
    )
    log.info("Subscription cancelled: user=%s (access immediately revoked)", user_id)

    await db["activity_logs"].insert_one({
        "user_id":    user_id,
        "type":       "subscription_cancelled",
        "action_type": "subscription_cancelled",
        "month_key":  _month_key(),
        "timestamp":  time.time(),
    })


async def _handle_subscription_updated(db, subscription: dict) -> None:
    """Handle customer.subscription.updated — sync interval and status."""
    cid = subscription.get("customer")
    if not cid:
        return

    user = await db["users"].find_one({"stripe_customer_id": cid})
    if not user:
        return

    user_id    = user["id"]
    sub_items  = subscription.get("items", {}).get("data", [])
    sub_status = subscription.get("status", "")

    # Ad Mode subscription update
    _is_ad_mode = any(
        item.get("price", {}).get("id", "") in AD_MODE_PRICES
        for item in sub_items
    )
    if _is_ad_mode:
        has_ad = sub_status in ("active", "trialing")
        await db["users"].update_one(
            {"id": user_id}, {"$set": {"has_ad_mode": has_ad}}
        )
        log.info("Ad Mode updated: user=%s status=%s", user_id, sub_status)
        return

    # Sync subscription active state + interval
    is_active = sub_status in ("active", "trialing")
    interval  = user.get("subscription_interval", "month")
    for item in sub_items:
        pid = item.get("price", {}).get("id", "")
        if pid in SUBSCRIPTION_PRICES:
            interval = SUBSCRIPTION_PRICES[pid]
            break

    period_end = subscription.get("current_period_end")
    updates: dict = {
        "is_subscribed":         is_active,
        "subscription_interval": interval,
    }
    if period_end:
        updates["subscription_end"] = period_end

    await db["users"].update_one({"id": user_id}, {"$set": updates})
    log.info("Subscription updated: user=%s status=%s interval=%s", user_id, sub_status, interval)


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

    # Auto-revoke after MAX_PAYMENT_FAILURES consecutive failures
    if failure_count >= MAX_PAYMENT_FAILURES and current_plan != "free":
        log.error(
            "AUTO-REVOKE: user=%s reached %d payment failures — revoking access",
            uid, failure_count,
        )
        await db["users"].update_one(
            {"id": uid},
            {"$set": {
                "is_subscribed":                   False,
                "plan":                            "free",
                "subscription_auto_downgraded_at": time.time(),
                "subscription_downgrade_reason":   f"payment_failed_{failure_count}x",
            }},
        )
        await db["activity_logs"].insert_one({
            "user_id":      uid,
            "type":         "auto_downgrade",
            "action_type":  "auto_downgrade",
            "month_key":    _month_key(),
            "timestamp":    time.time(),
            "details": {
                "reason":          "payment_failed",
                "failure_count":   failure_count,
                "previous_plan":   current_plan,
                "subscription_id": sub_id,
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
