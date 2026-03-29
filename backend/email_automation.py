"""
email_automation.py
Smart email automation background task for Mini Assistant AI — Phase 1 + integrated.

Runs every 10 minutes. Four triggers:
  A. followup_upgrade  — free users who got a welcome email 24–168h ago (no upgrade yet)
  B. low_credits       — subscribers with <20% credits left, no topup in 24h
  C. payment_failed    — users with payment_failure_count >= 1, not emailed in 24h
  D. reminder          — free users who got followup_upgrade 72h–14d ago, still free

Spam guard:
  - Max 1 email per type per user per 24h
  - Max 3 automated emails per user per 24h

Toggle via ENV:  EMAIL_AUTOMATION_ENABLED=true  (default true)
All emails logged with automated=True via email_logger.
"""

import asyncio
import logging
import os
import time

import resend

from email_design import (
    shell,
    header,
    feature_list,
    callout_box,
    credit_bar,
    info_box,
    PRICING_URL,
    BILLING_URL,
    SENDER,
)
from email_personalization import (
    personalize_subject,
    select_tone,
    get_tone_snippets,
    get_subject,
)
from email_growth import (
    assign_variant,
    get_ab_weight,
    evaluate_ab_winners,
    get_sequence_step,
    ONBOARDING_SEQUENCE,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ENABLED              = os.environ.get("EMAIL_AUTOMATION_ENABLED", "true").lower() == "true"
INTERVAL_SECONDS     = 600          # 10 minutes
WINDOW_24H           = 86400        # seconds
WINDOW_7D            = 7 * 86400
WINDOW_72H           = 3 * 86400
WINDOW_14D           = 14 * 86400
MAX_AUTO_PER_DAY     = 3
EMAIL_MAX_PER_RUN    = int(os.environ.get("EMAIL_MAX_PER_RUN", "500"))
CONVERSION_COOLDOWN  = WINDOW_24H   # skip automation if user converted within this window

# High-value user protection
HIGH_VALUE_ENABLED   = os.environ.get("HIGH_VALUE_PROTECTION", "true").lower() == "true"
HIGH_VALUE_THRESHOLD = float(os.environ.get("HIGH_VALUE_THRESHOLD", "100"))  # total USD spent
HIGH_VALUE_FREQUENCY = int(os.environ.get("HIGH_VALUE_FREQUENCY_HOURS", "48")) * 3600

_PLAN_LIMITS: dict = {
    "free":     50,
    "standard": 500,
    "pro":      2000,
    "max":      10000,
}
LOW_CREDIT_THRESHOLD = 0.20     # 20 %


# ---------------------------------------------------------------------------
# Email content templates — return (subject_base, content_html)
# ---------------------------------------------------------------------------

def _followup_upgrade_content(name: str) -> tuple:
    first = name.split()[0] if name else "there"
    subject_base = "Still thinking about upgrading? Here's what you're missing \U0001f680"
    content = (
        header(
            "Still thinking about upgrading? \U0001f680",
            f"Hey {first}, you're still on the free plan. Here's what you're missing:",
        )
        + feature_list(
            [
                "500 credits/month (10\u00d7 more)",
                "Full source code export",
                "Download as ZIP or push to GitHub",
                "Priority email support",
            ],
            label="Unlock with Standard",
        )
        + callout_box(
            "\U0001f4a1",
            "Pro &amp; Max plans available too",
            "Up to 10,000 credits/month \u00b7 Team seats \u00b7 Vercel deploy",
        )
    )
    return subject_base, content


def _low_credits_content(name: str, credits_left: int, plan: str) -> tuple:
    first = name.split()[0] if name else "there"
    subject_base = f"\u26a1 You have {credits_left:,} credits left \u2014 top up to keep building"
    content = (
        header(
            "Running low on credits \u26a1",
            f"Hey {first}, you're almost out of Mini Credits.",
        )
        + credit_bar(credits_left, _PLAN_LIMITS.get(plan, 500))
        + info_box(
            "Top-up packs (never expire)",
            "100 credits \u2014 300 credits \u2014 800 credits \u00b7 Stack on your monthly plan",
        )
    )
    return subject_base, content


def _payment_failed_content(name: str) -> tuple:
    first = name.split()[0] if name else "there"
    subject_base = "\u26a0\ufe0f Payment issue \u2014 please update your billing details"
    content = (
        header(
            "Payment issue \u2014 action needed \u26a0\ufe0f",
            f"Hey {first}, we couldn't process your last payment.",
        )
        + callout_box(
            "\U0001f534",
            "Payment failed",
            "Your card was declined. Update your payment method to avoid a plan downgrade.",
            "rgba(239,68,68,0.08)",
            "rgba(239,68,68,0.30)",
        )
        + info_box(
            "After <strong style=\"color:#ffffff;\">3 failed payments</strong>, "
            "your subscription will be automatically downgraded to the free plan.",
            "Questions? Reply to this email \u2014 we're happy to help.",
        )
    )
    return subject_base, content


def _reminder_content(name: str) -> tuple:
    first = name.split()[0] if name else "there"
    subject_base = "One last nudge \u2014 have you tried upgrading? \U0001f4a1"
    content = (
        header(
            "Still on the free plan? \U0001f4a1",
            f"Hey {first}, we noticed you haven't upgraded yet.",
        )
        + feature_list(
            [
                "500\u201310,000 credits/month based on plan",
                "Export full source code",
                "Push to GitHub &amp; deploy to Vercel",
                "No interruptions while you build",
            ],
            check_color="#7c3aed",
            label="What you unlock",
        )
        + callout_box(
            "\U0001f3af",
            "Upgrade takes 60 seconds",
            "Choose Standard, Pro, or Max. Cancel anytime.",
            "rgba(124,58,237,0.08)",
            "rgba(124,58,237,0.25)",
        )
    )
    return subject_base, content


# ---------------------------------------------------------------------------
# Conversion cooldown
# ---------------------------------------------------------------------------

async def _recently_converted(db, user_id: str) -> bool:
    """
    Return True if the user made ANY payment (subscription or top-up) in the last 24h.
    Covers two scenarios:
      1. Stripe webhook delay — plan field not updated yet after upgrade
      2. Top-up purchase — user just bought credits, no need to nudge immediately
    """
    try:
        user = await db["users"].find_one(
            {"id": user_id},
            {"last_payment_succeeded_at": 1, "last_topup_at": 1},
        )
        if not user:
            return False
        now        = time.time()
        last_paid  = user.get("last_payment_succeeded_at") or 0
        last_topup = user.get("last_topup_at") or 0
        return (now - max(last_paid, last_topup)) < CONVERSION_COOLDOWN
    except Exception as exc:
        log.warning("_recently_converted check failed (non-fatal): %s", exc)
        return False  # fail open — better to send than to crash


async def _is_high_value_user(db, user_id: str) -> bool:
    """
    Return True if user's total_spend >= HIGH_VALUE_THRESHOLD.
    High-value users get reduced automation frequency and skip aggressive triggers.
    """
    if not HIGH_VALUE_ENABLED:
        return False
    try:
        user = await db["users"].find_one({"id": user_id}, {"total_spend": 1})
        return (user or {}).get("total_spend", 0) >= HIGH_VALUE_THRESHOLD
    except Exception as exc:
        log.debug("_is_high_value_user check failed (non-fatal): %s", exc)
        return False


# ---------------------------------------------------------------------------
# Spam guard
# ---------------------------------------------------------------------------

async def _can_send(db, user_id: str, email_type: str, window: int = WINDOW_24H) -> bool:
    """
    Return True if this user can receive this automated email type right now.
    `window` controls the dedup window — use HIGH_VALUE_FREQUENCY for protected users.
    """
    # Fast pre-check: if last_automation_sent_at is within the last hour, skip
    # all DB log queries — protects against burst sends on large user bases.
    try:
        u = await db["users"].find_one({"id": user_id}, {"last_automation_sent_at": 1})
        if u:
            last_auto = u.get("last_automation_sent_at") or 0
            if (time.time() - last_auto) < min(3600, window):
                return False
    except Exception:
        pass  # fall through to full log check

    cutoff = time.time() - window

    # Rule 1: same type not already sent within the window
    same_type_count = await db["email_logs"].count_documents({
        "user_id":    user_id,
        "email_type": email_type,
        "automated":  True,
        "status":     "sent",
        "timestamp":  {"$gte": cutoff},
    })
    if same_type_count > 0:
        return False

    # Rule 2: total automated emails within window < MAX_AUTO_PER_DAY
    total_in_window = await db["email_logs"].count_documents({
        "user_id":   user_id,
        "automated": True,
        "timestamp": {"$gte": cutoff},
    })
    return total_in_window < MAX_AUTO_PER_DAY


# ---------------------------------------------------------------------------
# Shared send helper
# ---------------------------------------------------------------------------

async def _send_automated(
    db,
    user_id: str,
    to_email: str,
    email_type: str,
    subject_base: str,
    content_html: str,
    *,
    sequence: str | None = None,
    sequence_step: int | None = None,
) -> bool:
    """
    Personalise subject + tone, wrap content in shell, dispatch via email_logger.
    Returns True on success.
    """
    if not resend.api_key:
        log.warning("email_automation: RESEND_API_KEY not set — skipping %s", email_type)
        return False

    from email_logger import send_with_log   # noqa: PLC0415

    # Fetch current traffic weight then assign variant deterministically
    weight_a = await get_ab_weight(db, email_type)
    variant  = assign_variant(user_id, email_type, weight_a)

    # Fetch user for personalisation fields
    try:
        user = await db["users"].find_one(
            {"id": user_id},
            {"plan": 1, "name": 1, "subscription_credits": 1,
             "topup_credits": 1, "payment_failure_count": 1},
        ) or {}
    except Exception as exc:
        log.warning("_send_automated: could not fetch user %s: %s", user_id, exc)
        user = {}

    subject = await personalize_subject(email_type, variant, user, subject_base)

    tone = select_tone(user, email_type)
    _, closer = get_tone_snippets(tone)

    # Append closer as italic paragraph to content
    full_content = content_html
    if closer:
        full_content += (
            f'\n  <p style="margin:18px 0 0;font-size:12px;color:#64748b;'
            f'text-align:center;font-style:italic;'
            f'font-family:Inter,system-ui,-apple-system,sans-serif;">'
            f'{closer}</p>'
        )

    # CTA config
    if email_type == "payment_failed":
        cta_url   = BILLING_URL
        cta_label = "Update Billing"
    else:
        cta_url   = PRICING_URL
        cta_label = "View Plans"

    html = shell(
        full_content,
        cta_url,
        cta_label,
        footer_note="You're receiving this as an automated reminder from Mini Assistant AI.",
    )

    params: dict = {
        "from":    SENDER,
        "to":      [to_email],
        "subject": subject,
        "html":    html,
    }

    ok = await send_with_log(
        db=db,
        user_id=user_id,
        email=to_email,
        email_type=email_type,
        send_fn=resend.Emails.send,
        params=params,
        subject=subject,
        automated=True,
        variant=variant,
        sequence=sequence,
        sequence_step=sequence_step,
    )

    # Stamp user doc with send time — enables fast pre-check in _can_send
    if ok:
        try:
            await db["users"].update_one(
                {"id": user_id},
                {"$set": {"last_automation_sent_at": time.time()}},
            )
        except Exception as exc:
            log.warning("last_automation_sent_at update failed (non-fatal): %s", exc)

    return ok


# ---------------------------------------------------------------------------
# Trigger A: followup_upgrade
# ---------------------------------------------------------------------------

async def _check_followup_upgrades(db, budget: dict) -> int:
    """
    Find free users who got a welcome email 24–168h ago and haven't upgraded.
    Send them a 'Still thinking about upgrading?' nudge.
    Returns number of emails sent.
    """
    sent = 0
    now  = time.time()
    cutoff_min = now - WINDOW_7D    # don't go further back than 7 days
    cutoff_max = now - WINDOW_24H   # at least 24h must have passed

    # Get user_ids who received a welcome email in the 24h–7d window
    pipeline = [
        {"$match": {
            "email_type": "welcome",
            "status":     "sent",
            "timestamp":  {"$gte": cutoff_min, "$lte": cutoff_max},
        }},
        {"$group": {"_id": "$user_id", "email": {"$first": "$email"}}},
    ]
    candidates = await db["email_logs"].aggregate(pipeline).to_list(None)
    log.debug("followup_upgrade: %d candidates from welcome emails", len(candidates))

    for row in candidates:
        if budget["remaining"] <= 0:
            break

        user_id    = row["_id"]
        user_email = row["email"]

        # Confirm still on free plan
        user = await db["users"].find_one(
            {"id": user_id},
            {"plan": 1, "name": 1, "email": 1},
        )
        if not user or user.get("plan", "free") != "free":
            continue

        # High-value users skip aggressive upgrade nudges entirely
        if await _is_high_value_user(db, user_id):
            continue

        # Skip if user converted (paid) within the last 24h — guards webhook delay
        if await _recently_converted(db, user_id):
            continue

        if not await _can_send(db, user_id, "followup_upgrade"):
            continue

        name     = user.get("name", "")
        to_email = user.get("email") or user_email
        if not to_email:
            continue

        subject_base, content = _followup_upgrade_content(name)
        ok = await _send_automated(
            db, user_id, to_email, "followup_upgrade", subject_base, content,
            sequence="onboarding", sequence_step=1,
        )
        if ok:
            sent += 1
            budget["remaining"] -= 1

    return sent


# ---------------------------------------------------------------------------
# Trigger B: low_credits
# ---------------------------------------------------------------------------

async def _check_low_credits(db, budget: dict) -> int:
    """
    Find paid subscribers with < 20% credits left and no topup in the last 24h.
    Returns number of emails sent.
    """
    sent   = 0
    cutoff = time.time() - WINDOW_24H

    # Fetch all non-free users
    users = await db["users"].find(
        {"plan": {"$nin": ["free", None]}},
        {"id": 1, "email": 1, "name": 1, "plan": 1,
         "subscription_credits": 1, "topup_credits": 1},
    ).to_list(None)

    for user in users:
        if budget["remaining"] <= 0:
            break

        user_id  = user.get("id", "")
        to_email = user.get("email", "")
        if not user_id or not to_email:
            continue

        plan       = user.get("plan", "standard")
        plan_limit = _PLAN_LIMITS.get(plan, 500)
        sub_cr     = max(0, user.get("subscription_credits", 0) or 0)
        top_cr     = max(0, user.get("topup_credits", 0) or 0)
        total_cr   = sub_cr + top_cr

        # Check < 20% threshold
        if plan_limit <= 0 or total_cr >= plan_limit * LOW_CREDIT_THRESHOLD:
            continue

        # Check no topup purchase in last 24h
        recent_topup = await db["activity_logs"].count_documents({
            "user_id":     user_id,
            "action_type": "topup_purchase",
            "timestamp":   {"$gte": cutoff},
        })
        if recent_topup > 0:
            continue

        # High-value users: less frequent nudges (48h instead of 24h)
        hv     = await _is_high_value_user(db, user_id)
        window = HIGH_VALUE_FREQUENCY if hv else WINDOW_24H
        if not await _can_send(db, user_id, "low_credits", window=window):
            continue

        subject_base, content = _low_credits_content(user.get("name", ""), total_cr, plan)
        ok = await _send_automated(
            db, user_id, to_email, "low_credits", subject_base, content,
        )
        if ok:
            sent += 1
            budget["remaining"] -= 1

    return sent


# ---------------------------------------------------------------------------
# Trigger C: payment_failed
# ---------------------------------------------------------------------------

async def _check_payment_failed(db, budget: dict) -> int:
    """
    Find users with payment_failure_count >= 1 and no payment_failed email in 24h.
    Returns number of emails sent.
    """
    sent = 0

    users = await db["users"].find(
        {"payment_failure_count": {"$gte": 1}},
        {"id": 1, "email": 1, "name": 1, "payment_failure_count": 1},
    ).to_list(None)

    for user in users:
        if budget["remaining"] <= 0:
            break

        user_id  = user.get("id", "")
        to_email = user.get("email", "")
        if not user_id or not to_email:
            continue

        # Skip if they just paid successfully (webhook delay guard)
        if await _recently_converted(db, user_id):
            continue

        # High-value users: still send payment_failed (critical), but use 48h window
        hv     = await _is_high_value_user(db, user_id)
        window = HIGH_VALUE_FREQUENCY if hv else WINDOW_24H
        if not await _can_send(db, user_id, "payment_failed", window=window):
            continue

        subject_base, content = _payment_failed_content(user.get("name", ""))
        ok = await _send_automated(
            db, user_id, to_email, "payment_failed", subject_base, content,
        )
        if ok:
            sent += 1
            budget["remaining"] -= 1

    return sent


# ---------------------------------------------------------------------------
# Trigger D: reminder
# ---------------------------------------------------------------------------

async def _check_reminders(db, budget: dict) -> int:
    """
    Find free users who got a followup_upgrade email 72h–14d ago and are still free.
    Send them a final 'reminder' nudge.
    Returns number of emails sent.
    """
    sent = 0
    now  = time.time()
    cutoff_min = now - WINDOW_14D   # don't go further back than 14 days
    cutoff_max = now - WINDOW_72H   # at least 72h must have passed

    # Users who received followup_upgrade in the 72h–14d window
    pipeline = [
        {"$match": {
            "email_type": "followup_upgrade",
            "status":     "sent",
            "timestamp":  {"$gte": cutoff_min, "$lte": cutoff_max},
        }},
        {"$group": {"_id": "$user_id", "email": {"$first": "$email"}}},
    ]
    candidates = await db["email_logs"].aggregate(pipeline).to_list(None)
    log.debug("reminder: %d candidates from followup_upgrade emails", len(candidates))

    for row in candidates:
        if budget["remaining"] <= 0:
            break

        user_id    = row["_id"]
        user_email = row["email"]

        # Confirm still on free plan
        user = await db["users"].find_one(
            {"id": user_id},
            {"plan": 1, "name": 1, "email": 1},
        )
        if not user or user.get("plan", "free") != "free":
            continue

        # High-value users skip aggressive reminder nudges entirely
        if await _is_high_value_user(db, user_id):
            continue

        # Skip if they just converted (webhook delay guard)
        if await _recently_converted(db, user_id):
            continue

        if not await _can_send(db, user_id, "reminder"):
            continue

        name     = user.get("name", "")
        to_email = user.get("email") or user_email
        if not to_email:
            continue

        subject_base, content = _reminder_content(name)
        ok = await _send_automated(
            db, user_id, to_email, "reminder", subject_base, content,
            sequence="onboarding", sequence_step=2,
        )
        if ok:
            sent += 1
            budget["remaining"] -= 1

    return sent


# ---------------------------------------------------------------------------
# Background loop
# ---------------------------------------------------------------------------

async def _run_once(db) -> None:
    """Run all four triggers once. Catches all exceptions per-trigger."""
    log.info("email_automation: running triggers")

    # Shared budget — enforces global cap across all triggers in one run
    budget = {"remaining": EMAIL_MAX_PER_RUN}

    for label, trigger_fn, args in [
        ("followup_upgrade", _check_followup_upgrades, (db, budget)),
        ("low_credits",      _check_low_credits,       (db, budget)),
        ("payment_failed",   _check_payment_failed,    (db, budget)),
        ("reminder",         _check_reminders,         (db, budget)),
    ]:
        if budget["remaining"] <= 0:
            log.warning(
                "email_automation: global send limit (%d) reached — stopping run early",
                EMAIL_MAX_PER_RUN,
            )
            break
        try:
            count = await trigger_fn(*args)
            if count:
                log.info("email_automation: %s → sent %d email(s)", label, count)
        except Exception as exc:
            log.error("email_automation: %s trigger failed: %s", label, exc)

    sent_total = EMAIL_MAX_PER_RUN - budget["remaining"]
    if sent_total:
        log.info("email_automation: run complete — %d total email(s) sent", sent_total)

    # Evaluate A/B winners and shift traffic weights (non-fatal, runs every loop)
    try:
        await evaluate_ab_winners(db)
    except Exception as exc:
        log.warning("email_automation: evaluate_ab_winners failed (non-fatal): %s", exc)


async def start_email_automation(db) -> None:
    """
    Start the automation loop as a background asyncio task.
    Should be called once from server startup.
    """
    if not ENABLED:
        log.info("email_automation: disabled (EMAIL_AUTOMATION_ENABLED=false)")
        return

    async def _loop():
        log.info("email_automation: background task started (interval=%ds)", INTERVAL_SECONDS)
        while True:
            try:
                await _run_once(db)
            except Exception as exc:
                log.error("email_automation: loop error: %s", exc)
            await asyncio.sleep(INTERVAL_SECONDS)

    asyncio.create_task(_loop())
    log.info("email_automation: task scheduled")
