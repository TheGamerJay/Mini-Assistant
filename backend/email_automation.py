"""
email_automation.py
Smart email automation background task for Mini Assistant AI.

Runs every 10 minutes. Three triggers:
  A. followup_upgrade  — free users who got a welcome email 24–168h ago (no upgrade yet)
  B. low_credits       — subscribers with <20% credits left, no topup in 24h
  C. payment_failed    — users with payment_failure_count >= 1, not emailed in 24h

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

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ENABLED           = os.environ.get("EMAIL_AUTOMATION_ENABLED", "true").lower() == "true"
INTERVAL_SECONDS  = 600          # 10 minutes
WINDOW_24H        = 86400        # seconds
WINDOW_7D         = 7 * 86400
MAX_AUTO_PER_DAY  = 3

_PLAN_LIMITS: dict[str, int] = {
    "free":     50,
    "standard": 500,
    "pro":      2000,
    "max":      10000,
    "team":     10000,
}
LOW_CREDIT_THRESHOLD = 0.20     # 20 %

SENDER       = "Mini Assistant AI <onboarding@resend.dev>"
FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://miniassistantai.com")
PRICING_URL  = f"{FRONTEND_URL}/pricing"
BILLING_URL  = f"{FRONTEND_URL}/dashboard"   # where they manage billing


# ---------------------------------------------------------------------------
# HTML shell (mirrors email_sender._shell — kept local to avoid circular import)
# ---------------------------------------------------------------------------

def _stamp() -> str:
    return f"""
<table width="100%" cellpadding="0" cellspacing="0" style="margin-top:20px;">
  <tr><td>
    <hr style="border:none;border-top:1px solid #1e2030;margin:0 0 14px;" />
    <p style="margin:0;font-size:12px;color:#888888;text-align:center;line-height:1.6;">
      Powered by
      <a href="{FRONTEND_URL}" style="color:#888888;text-decoration:none;font-weight:600;">
        Mini Assistant AI
      </a>
    </p>
    <p style="margin:4px 0 0;font-size:11px;color:#555555;text-align:center;">
      Build apps, chat with AI, ship faster.
    </p>
  </td></tr>
</table>"""


def _shell(content_html: str, cta_url: str, cta_label: str, footer_note: str = "") -> str:
    note = (
        f'<p style="margin:6px 0 0;font-size:10px;color:#334155;text-align:center;">{footer_note}</p>'
        if footer_note else ""
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Mini Assistant AI</title>
</head>
<body style="margin:0;padding:0;background:#0d0d12;
             font-family:Inter,system-ui,-apple-system,sans-serif;color:#e2e8f0;">
  <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
         style="background:#0d0d12;min-height:100vh;">
    <tr><td align="center" style="padding:40px 16px;">
      <table width="100%" style="max-width:520px;" cellpadding="0" cellspacing="0"
             role="presentation">

        <!-- Logo wordmark -->
        <tr><td align="center" style="padding-bottom:28px;">
          <span style="display:inline-flex;align-items:center;gap:10px;">
            <span style="display:inline-block;width:32px;height:32px;border-radius:8px;
                         background:linear-gradient(135deg,#06b6d4,#7c3aed);"></span>
            <span style="font-size:17px;font-weight:700;color:#ffffff;letter-spacing:-0.4px;">
              Mini Assistant AI
            </span>
          </span>
        </td></tr>

        <!-- Card -->
        <tr><td style="background:#111118;border:1px solid rgba(255,255,255,0.08);
                       border-radius:20px;padding:36px 32px;">

          {content_html}

          <!-- CTA -->
          <table width="100%" cellpadding="0" cellspacing="0"
                 role="presentation" style="padding-top:28px;">
            <tr><td align="center">
              <a href="{cta_url}"
                 style="display:inline-block;
                        background:linear-gradient(135deg,#06b6d4,#7c3aed);
                        color:#ffffff;font-size:14px;font-weight:700;
                        text-decoration:none;padding:14px 32px;
                        border-radius:12px;letter-spacing:0.2px;">
                {cta_label} →
              </a>
            </td></tr>
          </table>

        </td></tr>

        <!-- Footer -->
        <tr><td align="center" style="padding-top:20px;">
          <p style="margin:0;font-size:11px;color:#475569;text-align:center;">
            Mini Assistant AI ·
            <a href="{FRONTEND_URL}" style="color:#06b6d4;text-decoration:none;">
              miniassistantai.com
            </a>
          </p>
          {note}
          {_stamp()}
        </td></tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Email templates
# ---------------------------------------------------------------------------

def _followup_upgrade_html(name: str) -> tuple[str, str]:
    first = name.split()[0] if name else "there"
    content = f"""
      <h1 style="margin:0 0 8px;font-size:26px;font-weight:800;color:#ffffff;
                 letter-spacing:-0.5px;text-align:center;">
        Still thinking about upgrading? 🚀
      </h1>
      <p style="margin:0 0 22px;font-size:14px;color:#94a3b8;
                line-height:1.7;text-align:center;">
        Hey {first}, you're still on the free plan.<br />
        Here's what you're missing out on:
      </p>

      <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
             style="background:rgba(255,255,255,0.03);
                    border:1px solid rgba(255,255,255,0.06);
                    border-radius:14px;padding:18px 22px;margin-bottom:18px;">
        <tr><td style="padding-bottom:10px;font-size:11px;font-weight:700;
                       color:#475569;text-transform:uppercase;letter-spacing:1.5px;">
          Unlock with Standard ($9/mo)
        </td></tr>
        <tr><td style="padding:5px 0;font-size:13px;color:#cbd5e1;">
          <span style="color:#06b6d4;margin-right:10px;">✓</span>500 credits/month (10× more)
        </td></tr>
        <tr><td style="padding:5px 0;font-size:13px;color:#cbd5e1;">
          <span style="color:#06b6d4;margin-right:10px;">✓</span>Full source code export (HTML, CSS, JS)
        </td></tr>
        <tr><td style="padding:5px 0;font-size:13px;color:#cbd5e1;">
          <span style="color:#06b6d4;margin-right:10px;">✓</span>Download as ZIP or push to GitHub
        </td></tr>
        <tr><td style="padding:5px 0;font-size:13px;color:#cbd5e1;">
          <span style="color:#06b6d4;margin-right:10px;">✓</span>Priority email support
        </td></tr>
      </table>

      <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
             style="background:rgba(6,182,212,0.08);border:1px solid rgba(6,182,212,0.25);
                    border-radius:12px;padding:14px 18px;">
        <tr>
          <td style="font-size:20px;width:32px;">💡</td>
          <td style="padding-left:10px;">
            <p style="margin:0;font-size:13px;font-weight:700;color:#ffffff;">
              Pro &amp; Max plans available too
            </p>
            <p style="margin:3px 0 0;font-size:11px;color:#64748b;">
              Up to 10,000 credits/month · Team seats · Vercel deploy
            </p>
          </td>
        </tr>
      </table>
    """
    subject = "Still thinking about upgrading? Here's what you're missing 🚀"
    html    = _shell(content, PRICING_URL, "See All Plans",
                     footer_note="You're receiving this as a Mini Assistant AI free-plan user.")
    return subject, html


def _low_credits_html(name: str, credits_left: int, plan: str) -> tuple[str, str]:
    first      = name.split()[0] if name else "there"
    plan_limit = _PLAN_LIMITS.get(plan, 500)
    pct        = max(0, round(credits_left / plan_limit * 100)) if plan_limit else 0
    bar_width  = max(2, pct)   # minimum 2 % for visual
    content = f"""
      <h1 style="margin:0 0 8px;font-size:26px;font-weight:800;color:#ffffff;
                 letter-spacing:-0.5px;text-align:center;">
        Running low on credits ⚡
      </h1>
      <p style="margin:0 0 22px;font-size:14px;color:#94a3b8;
                line-height:1.7;text-align:center;">
        Hey {first}, you're almost out of Mini Credits.<br />
        Top up now to keep building without interruption.
      </p>

      <!-- Credit gauge -->
      <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
             style="background:rgba(245,158,11,0.08);
                    border:1px solid rgba(245,158,11,0.30);
                    border-radius:14px;padding:20px 22px;margin-bottom:18px;">
        <tr><td>
          <p style="margin:0 0 10px;font-size:13px;color:#94a3b8;">
            Credits remaining:
            <strong style="color:#f59e0b;font-size:16px;"> {credits_left:,}</strong>
            <span style="color:#64748b;font-size:11px;"> / {plan_limit:,}</span>
          </p>
          <!-- Progress bar -->
          <div style="background:#1e2030;border-radius:99px;height:8px;overflow:hidden;">
            <div style="background:#f59e0b;height:8px;width:{bar_width}%;border-radius:99px;"></div>
          </div>
          <p style="margin:8px 0 0;font-size:11px;color:#64748b;">
            {pct}% remaining · 1 chat = 1 credit · 1 image = 3 credits
          </p>
        </td></tr>
      </table>

      <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
             style="background:rgba(255,255,255,0.03);
                    border:1px solid rgba(255,255,255,0.06);
                    border-radius:12px;padding:14px 18px;">
        <tr><td>
          <p style="margin:0;font-size:13px;font-weight:700;color:#ffffff;">
            Top-up packs (never expire)
          </p>
          <p style="margin:4px 0 0;font-size:12px;color:#94a3b8;">
            100 credits — 300 credits — 800 credits
          </p>
          <p style="margin:4px 0 0;font-size:11px;color:#475569;">
            Top-up credits stack on top of your monthly plan.
          </p>
        </td></tr>
      </table>
    """
    subject = f"⚡ You have {credits_left:,} credits left — top up to keep building"
    html    = _shell(content, PRICING_URL, "Top Up Credits",
                     footer_note="You're receiving this because your credit balance is low.")
    return subject, html


def _payment_failed_html(name: str) -> tuple[str, str]:
    first = name.split()[0] if name else "there"
    content = f"""
      <h1 style="margin:0 0 8px;font-size:26px;font-weight:800;color:#ffffff;
                 letter-spacing:-0.5px;text-align:center;">
        Payment issue — action needed ⚠️
      </h1>
      <p style="margin:0 0 22px;font-size:14px;color:#94a3b8;
                line-height:1.7;text-align:center;">
        Hey {first}, we couldn't process your last payment.<br />
        Please update your billing details to keep your plan active.
      </p>

      <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
             style="background:rgba(239,68,68,0.08);
                    border:1px solid rgba(239,68,68,0.30);
                    border-radius:14px;padding:20px 22px;margin-bottom:18px;">
        <tr>
          <td style="font-size:22px;width:36px;">🔴</td>
          <td style="padding-left:12px;">
            <p style="margin:0;font-size:13px;font-weight:700;color:#ffffff;">
              Payment failed
            </p>
            <p style="margin:4px 0 0;font-size:12px;color:#94a3b8;">
              Your card was declined. Update your payment method to avoid a plan downgrade.
            </p>
          </td>
        </tr>
      </table>

      <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
             style="background:rgba(255,255,255,0.03);
                    border:1px solid rgba(255,255,255,0.06);
                    border-radius:12px;padding:14px 18px;">
        <tr><td>
          <p style="margin:0;font-size:13px;color:#94a3b8;">
            After <strong style="color:#ffffff;">3 failed payments</strong>,
            your subscription will be automatically downgraded to the free plan.
          </p>
          <p style="margin:6px 0 0;font-size:11px;color:#475569;">
            Questions? Reply to this email — we're happy to help.
          </p>
        </td></tr>
      </table>
    """
    subject = "⚠️ Payment issue — please update your billing details"
    html    = _shell(content, BILLING_URL, "Update Billing",
                     footer_note="You're receiving this because a payment to Mini Assistant AI failed.")
    return subject, html


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
        user_id   = row["_id"]
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

        name    = user.get("name", "")
        to_email = user.get("email") or user_email
        if not to_email:
            continue

        subject, html = _followup_upgrade_html(name)
        ok = await _send_automated(db, user_id, to_email, "followup_upgrade", subject, html)
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
        sub_cr     = max(0, user.get("subscription_credits", 0))
        top_cr     = max(0, user.get("topup_credits", 0))
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

        subject, html = _low_credits_html(user.get("name", ""), total_cr, plan)
        ok = await _send_automated(db, user_id, to_email, "low_credits", subject, html)
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

        subject, html = _payment_failed_html(user.get("name", ""))
        ok = await _send_automated(db, user_id, to_email, "payment_failed", subject, html)
        if ok:
            sent += 1

    return sent


# ---------------------------------------------------------------------------
# Shared send helper
# ---------------------------------------------------------------------------

async def _send_automated(
    db,
    user_id: str,
    to_email: str,
    email_type: str,
    subject: str,
    html: str,
) -> bool:
    """Build Resend params and dispatch via email_logger with automated=True."""
    if not resend.api_key:
        log.warning("email_automation: RESEND_API_KEY not set — skipping %s", email_type)
        return False

    from email_logger import send_with_log   # noqa: PLC0415

    params: resend.Emails.SendParams = {
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
    )


# ---------------------------------------------------------------------------
# Background loop
# ---------------------------------------------------------------------------

async def _run_once(db) -> None:
    """Run all three triggers once. Catches all exceptions per-trigger."""
    log.info("email_automation: running triggers")

    for label, coro in [
        ("followup_upgrade", _check_followup_upgrades(db)),
        ("low_credits",      _check_low_credits(db)),
        ("payment_failed",   _check_payment_failed(db)),
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
