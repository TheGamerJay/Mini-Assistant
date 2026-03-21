"""
email_sender.py
Transactional email for Mini Assistant AI — welcome emails + top-up confirmations.

Supports two providers (in priority order):
  1. SendGrid  — set SENDGRID_API_KEY env var
  2. SMTP      — set SMTP_HOST, SMTP_USER, SMTP_PASS (and optionally SMTP_PORT, SMTP_FROM)

If neither is configured, email sending is skipped with a warning log.
All errors are non-fatal — a failed email never breaks the webhook flow.
"""

import logging
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SENDGRID_API_KEY  = os.environ.get("SENDGRID_API_KEY", "")
SMTP_HOST         = os.environ.get("SMTP_HOST", "")
SMTP_PORT         = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER         = os.environ.get("SMTP_USER", "")
SMTP_PASS         = os.environ.get("SMTP_PASS", "")
EMAIL_FROM        = os.environ.get("EMAIL_FROM", "noreply@miniassistantai.com")
EMAIL_FROM_NAME   = os.environ.get("EMAIL_FROM_NAME", "Mini Assistant AI")
FRONTEND_URL      = os.environ.get("FRONTEND_URL", "https://miniassistantai.com")

_EMAIL_AVAILABLE  = bool(SENDGRID_API_KEY or (SMTP_HOST and SMTP_USER and SMTP_PASS))

if not _EMAIL_AVAILABLE:
    log.info(
        "Email sender: no provider configured. "
        "Set SENDGRID_API_KEY or SMTP_HOST+SMTP_USER+SMTP_PASS to enable welcome emails."
    )

# ---------------------------------------------------------------------------
# Plan metadata
# ---------------------------------------------------------------------------
PLAN_META: dict[str, dict] = {
    "standard": {
        "display":  "Standard",
        "credits":  "500",
        "color":    "#06b6d4",
        "features": [
            "500 Mini Credits per month",
            "Full source code access (HTML, CSS, JS)",
            "Download projects as HTML & ZIP",
            "Push directly to GitHub",
            "Email support",
        ],
    },
    "pro": {
        "display":  "Pro",
        "credits":  "2,000",
        "color":    "#7c3aed",
        "features": [
            "2,000 Mini Credits per month",
            "One-click deploy to Vercel",
            "Full-stack project export",
            "Priority AI model access",
            "Priority support (1-day response)",
        ],
    },
    "max": {
        "display":  "Max",
        "credits":  "10,000",
        "color":    "#f59e0b",
        "features": [
            "10,000 Mini Credits per month",
            "Up to 10 team seats",
            "Shared credit pool",
            "Admin dashboard & usage analytics",
            "Dedicated support channel",
        ],
    },
}

# ---------------------------------------------------------------------------
# HTML email templates
# ---------------------------------------------------------------------------

def _base_template(content_html: str, cta_url: str, cta_label: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Mini Assistant AI</title>
</head>
<body style="margin:0;padding:0;background:#0d0d12;font-family:Inter,system-ui,-apple-system,sans-serif;color:#e2e8f0;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0d0d12;min-height:100vh;">
    <tr><td align="center" style="padding:40px 16px;">
      <table width="100%" style="max-width:520px;" cellpadding="0" cellspacing="0">

        <!-- Logo -->
        <tr><td align="center" style="padding-bottom:28px;">
          <div style="display:inline-flex;align-items:center;gap:10px;">
            <div style="width:36px;height:36px;border-radius:10px;background:linear-gradient(135deg,#06b6d4,#7c3aed);display:inline-block;"></div>
            <span style="font-size:18px;font-weight:700;color:#ffffff;letter-spacing:-0.5px;">Mini Assistant AI</span>
          </div>
        </td></tr>

        <!-- Card -->
        <tr><td style="background:#111118;border:1px solid rgba(255,255,255,0.08);border-radius:20px;padding:36px 32px;">
          {content_html}

          <!-- CTA button -->
          <tr><td align="center" style="padding-top:28px;">
            <a href="{cta_url}"
               style="display:inline-block;background:linear-gradient(135deg,#06b6d4,#7c3aed);
                      color:#ffffff;font-size:14px;font-weight:700;text-decoration:none;
                      padding:14px 32px;border-radius:12px;letter-spacing:0.2px;">
              {cta_label} →
            </a>
          </td></tr>
        </td></tr>

        <!-- Footer -->
        <tr><td align="center" style="padding-top:24px;">
          <p style="font-size:11px;color:#475569;margin:0;">
            Mini Assistant AI · Questions? Reply to this email or visit
            <a href="{FRONTEND_URL}" style="color:#06b6d4;text-decoration:none;">miniassistantai.com</a>
          </p>
          <p style="font-size:10px;color:#334155;margin:8px 0 0;">
            You're receiving this because you made a purchase. Payments processed by Stripe.
          </p>
          <!-- Stamp -->
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
          </table>
        </td></tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _welcome_html(name: str, plan_key: str, credits: int) -> tuple[str, str]:
    """Returns (subject, html_body) for a plan upgrade welcome email."""
    meta = PLAN_META.get(plan_key, PLAN_META["standard"])
    plan_display = meta["display"]
    color        = meta["color"]
    features_html = "".join(
        f'<li style="margin:0 0 8px;padding-left:8px;font-size:13px;color:#cbd5e1;">'
        f'<span style="color:{color};margin-right:8px;">✓</span>{f}</li>'
        for f in meta["features"]
    )

    first = name.split()[0] if name else "there"
    subject = f"🎉 Welcome to Mini Assistant {plan_display}!"
    content = f"""
      <h1 style="margin:0 0 6px;font-size:26px;font-weight:800;color:#ffffff;letter-spacing:-0.5px;">
        You're on {plan_display}! 🎉
      </h1>
      <p style="margin:0 0 20px;font-size:14px;color:#94a3b8;line-height:1.6;">
        Hey {first}, your upgrade is live. Here's what you now have access to:
      </p>

      <div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);
                  border-radius:14px;padding:20px 24px;margin-bottom:20px;">
        <p style="margin:0 0 12px;font-size:11px;font-weight:700;color:#64748b;
                  text-transform:uppercase;letter-spacing:1.5px;">What's Unlocked</p>
        <ul style="margin:0;padding:0;list-style:none;">
          {features_html}
        </ul>
      </div>

      <div style="background:{color}18;border:1px solid {color}40;border-radius:12px;
                  padding:14px 18px;display:flex;align-items:center;gap:12px;">
        <span style="font-size:22px;">⚡</span>
        <div>
          <p style="margin:0;font-size:13px;font-weight:700;color:#ffffff;">
            {credits:,} credits available now
          </p>
          <p style="margin:2px 0 0;font-size:11px;color:#64748b;">
            Resets monthly · 1 chat = 1 credit · 1 image = 3 credits
          </p>
        </div>
      </div>
    """
    body = _base_template(content, f"{FRONTEND_URL}/?checkout=already_handled", "Start Building")
    return subject, body


def _topup_html(name: str, credits_added: int, new_balance: int) -> tuple[str, str]:
    """Returns (subject, html_body) for a top-up confirmation email."""
    first   = name.split()[0] if name else "there"
    subject = f"⚡ {credits_added:,} credits added to your account"
    content = f"""
      <h1 style="margin:0 0 6px;font-size:26px;font-weight:800;color:#ffffff;letter-spacing:-0.5px;">
        Credits Added! ⚡
      </h1>
      <p style="margin:0 0 20px;font-size:14px;color:#94a3b8;line-height:1.6;">
        Hey {first}, your credit top-up is live and ready to use.
      </p>

      <div style="background:rgba(245,158,11,0.08);border:1px solid rgba(245,158,11,0.25);
                  border-radius:14px;padding:20px 24px;margin-bottom:20px;text-align:center;">
        <p style="margin:0;font-size:42px;font-weight:900;color:#f59e0b;letter-spacing:-1px;">
          +{credits_added:,}
        </p>
        <p style="margin:4px 0 0;font-size:12px;color:#94a3b8;font-weight:600;">
          credits added instantly
        </p>
      </div>

      <div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);
                  border-radius:12px;padding:14px 18px;">
        <p style="margin:0;font-size:13px;color:#94a3b8;">
          New balance: <strong style="color:#ffffff;">{new_balance:,} credits</strong>
        </p>
        <p style="margin:4px 0 0;font-size:11px;color:#475569;">
          Top-up credits never expire and stack on your monthly plan credits.
        </p>
      </div>
    """
    body = _base_template(content, f"{FRONTEND_URL}", "Start Building")
    return subject, body


# ---------------------------------------------------------------------------
# Low-level send
# ---------------------------------------------------------------------------

async def _send(to_email: str, to_name: str, subject: str, html_body: str) -> bool:
    """
    Send an email. Tries SendGrid first, then SMTP.
    Returns True on success, False on failure. Never raises.
    """
    if not _EMAIL_AVAILABLE:
        log.debug("Email skipped (no provider): subject=%s to=%s", subject, to_email)
        return False

    try:
        if SENDGRID_API_KEY:
            return await _send_sendgrid(to_email, to_name, subject, html_body)
        return await _send_smtp(to_email, to_name, subject, html_body)
    except Exception as exc:
        log.error("Email send failed (to=%s subject=%s): %s", to_email, subject, exc)
        return False


async def _send_sendgrid(to_email: str, to_name: str, subject: str, html_body: str) -> bool:
    import httpx   # noqa: PLC0415
    payload = {
        "personalizations": [{"to": [{"email": to_email, "name": to_name}]}],
        "from": {"email": EMAIL_FROM, "name": EMAIL_FROM_NAME},
        "subject": subject,
        "content": [{"type": "text/html", "value": html_body}],
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            "https://api.sendgrid.com/v3/mail/send",
            json=payload,
            headers={"Authorization": f"Bearer {SENDGRID_API_KEY}"},
        )
    if resp.status_code in (200, 202):
        log.info("Email sent via SendGrid: to=%s subject=%s", to_email, subject)
        return True
    log.warning("SendGrid error %d for %s: %s", resp.status_code, to_email, resp.text[:200])
    return False


async def _send_smtp(to_email: str, to_name: str, subject: str, html_body: str) -> bool:
    import asyncio, smtplib   # noqa: PLC0415

    def _blocking_send():
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"{EMAIL_FROM_NAME} <{EMAIL_FROM}>"
        msg["To"]      = f"{to_name} <{to_email}>" if to_name else to_email
        msg.attach(MIMEText(html_body, "html"))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(EMAIL_FROM, to_email, msg.as_string())

    await asyncio.get_event_loop().run_in_executor(None, _blocking_send)
    log.info("Email sent via SMTP: to=%s subject=%s", to_email, subject)
    return True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def send_welcome_email(
    to_email: str,
    to_name: str,
    plan: str,
    credits: int,
) -> bool:
    """Send a plan upgrade welcome email. Non-fatal."""
    try:
        subject, html = _welcome_html(to_name, plan, credits)
        return await _send(to_email, to_name, subject, html)
    except Exception as exc:
        log.error("send_welcome_email failed: %s", exc)
        return False


async def send_topup_email(
    to_email: str,
    to_name: str,
    credits_added: int,
    new_balance: int,
) -> bool:
    """Send a top-up confirmation email. Non-fatal."""
    try:
        subject, html = _topup_html(to_name, credits_added, new_balance)
        return await _send(to_email, to_name, subject, html)
    except Exception as exc:
        log.error("send_topup_email failed: %s", exc)
        return False
