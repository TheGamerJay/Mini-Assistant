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
    get_sequence_step,
    ONBOARDING_SEQUENCE,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ENABLED           = os.environ.get("EMAIL_AUTOMATION_ENABLED", "true").lower() == "true"
INTERVAL_SECONDS  = 600          # 10 minutes
WINDOW_24H        = 86400        # seconds
WINDOW_7D         = 7 * 86400
WINDOW_72H        = 3 * 86400
WINDOW_14D        = 14 * 86400
MAX_AUTO_PER_DAY  = 3

_PLAN_LIMITS: dict = {
    "free":     50,
    "standard": 500,
    "pro":      2000,
    "max":      10000,
    "team":     10000,
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
# Spam guard
# ---------------------------------------------------------------------------

async def _can_send(db, user_id: str, email_type: str) -> bool:
    """Return True if this user can receive this automated email type right now."""
    cutoff = time.time() - WINDOW_24H

    # Rule 1: same type not already sent in 24h
    same_type_count = await db["email_logs"].count_documents({
        "user_id":    user_id,
        "email_type": email_type,
        "automated":  True,
        "status":     "sent",
        "timestamp":  {"$gte": cutoff},
    })
    if same_type_count > 0:
        return False

    # Rule 2: total automated emails today < MAX_AUTO_PER_DAY
    total_today = await db["email_logs"].count_documents({
        "user_id":   user_id,
        "automated": True,
        "timestamp": {"$gte": cutoff},
    })
    return total_today < MAX_AUTO_PER_DAY


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

    variant = assign_variant(user_id, email_type)

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

    return await send_with_log(
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


# ---------------------------------------------------------------------------
# Trigger A: followup_upgrade
# ---------------------------------------------------------------------------

async def _check_followup_upgrades(db) -> int:
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
        user_id    = row["_id"]
        user_email = row["email"]

        # Confirm still on free plan
        user = await db["users"].find_one(
            {"id": user_id},
            {"plan": 1, "name": 1, "email": 1},
        )
        if not user or user.get("plan", "free") != "free":
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

    return sent


# ---------------------------------------------------------------------------
# Trigger B: low_credits
# ---------------------------------------------------------------------------

async def _check_low_credits(db) -> int:
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

        if not await _can_send(db, user_id, "low_credits"):
            continue

        subject_base, content = _low_credits_content(user.get("name", ""), total_cr, plan)
        ok = await _send_automated(
            db, user_id, to_email, "low_credits", subject_base, content,
        )
        if ok:
            sent += 1

    return sent


# ---------------------------------------------------------------------------
# Trigger C: payment_failed
# ---------------------------------------------------------------------------

async def _check_payment_failed(db) -> int:
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
        user_id  = user.get("id", "")
        to_email = user.get("email", "")
        if not user_id or not to_email:
            continue

        if not await _can_send(db, user_id, "payment_failed"):
            continue

        subject_base, content = _payment_failed_content(user.get("name", ""))
        ok = await _send_automated(
            db, user_id, to_email, "payment_failed", subject_base, content,
        )
        if ok:
            sent += 1

    return sent


# ---------------------------------------------------------------------------
# Trigger D: reminder
# ---------------------------------------------------------------------------

async def _check_reminders(db) -> int:
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
        user_id    = row["_id"]
        user_email = row["email"]

        # Confirm still on free plan
        user = await db["users"].find_one(
            {"id": user_id},
            {"plan": 1, "name": 1, "email": 1},
        )
        if not user or user.get("plan", "free") != "free":
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

    return sent


# ---------------------------------------------------------------------------
# Background loop
# ---------------------------------------------------------------------------

async def _run_once(db) -> None:
    """Run all four triggers once. Catches all exceptions per-trigger."""
    log.info("email_automation: running triggers")

    for label, coro in [
        ("followup_upgrade", _check_followup_upgrades(db)),
        ("low_credits",      _check_low_credits(db)),
        ("payment_failed",   _check_payment_failed(db)),
        ("reminder",         _check_reminders(db)),
    ]:
        try:
            count = await coro
            if count:
                log.info("email_automation: %s → sent %d email(s)", label, count)
        except Exception as exc:
            log.error("email_automation: %s trigger failed: %s", label, exc)


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
