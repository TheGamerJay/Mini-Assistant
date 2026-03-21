"""
email_sender.py
Resend-based transactional email for Mini Assistant AI.
Handles subscription upgrade (welcome) and credit top-up confirmation emails.
Triggered from Stripe webhooks — all errors are non-fatal.
"""

import logging
import os

import resend

resend.api_key = os.environ.get("RESEND_API_KEY", "")

log = logging.getLogger(__name__)

SENDER      = "Mini Assistant AI <onboarding@resend.dev>"
FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://miniassistantai.com")

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
# Shared footer stamp
# ---------------------------------------------------------------------------
_STAMP = f"""
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
"""

# ---------------------------------------------------------------------------
# Base shell
# ---------------------------------------------------------------------------

def _shell(content_html: str, cta_url: str, cta_label: str) -> str:
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
          <p style="margin:6px 0 0;font-size:10px;color:#334155;text-align:center;">
            You're receiving this because you made a purchase.
            Payments processed by Stripe.
          </p>
          {_STAMP}
        </td></tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Template builders
# ---------------------------------------------------------------------------

def _welcome_html(name: str, plan_key: str, credits: int) -> tuple[str, str]:
    meta         = PLAN_META.get(plan_key, PLAN_META["standard"])
    plan_display = meta["display"]
    color        = meta["color"]
    first        = name.split()[0] if name else "there"

    features_rows = "".join(
        f'<tr><td style="padding:5px 0;font-size:13px;color:#cbd5e1;">'
        f'<span style="color:{color};margin-right:10px;">✓</span>{f}</td></tr>'
        for f in meta["features"]
    )

    content = f"""
      <h1 style="margin:0 0 8px;font-size:26px;font-weight:800;color:#ffffff;
                 letter-spacing:-0.5px;text-align:center;">
        You're on {plan_display}! 🎉
      </h1>
      <p style="margin:0 0 22px;font-size:14px;color:#94a3b8;
                line-height:1.7;text-align:center;">
        Hey {first}, your upgrade is live. Here's what you now have access to:
      </p>

      <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
             style="background:rgba(255,255,255,0.03);
                    border:1px solid rgba(255,255,255,0.06);
                    border-radius:14px;padding:18px 22px;margin-bottom:18px;">
        <tr><td style="padding-bottom:10px;font-size:11px;font-weight:700;
                       color:#475569;text-transform:uppercase;letter-spacing:1.5px;">
          What's Unlocked
        </td></tr>
        {features_rows}
      </table>

      <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
             style="background:{color}18;border:1px solid {color}40;
                    border-radius:12px;padding:14px 18px;">
        <tr>
          <td style="font-size:20px;width:32px;">⚡</td>
          <td style="padding-left:10px;">
            <p style="margin:0;font-size:13px;font-weight:700;color:#ffffff;">
              {credits:,} credits available now
            </p>
            <p style="margin:3px 0 0;font-size:11px;color:#64748b;">
              Resets monthly · 1 chat = 1 credit · 1 image = 3 credits
            </p>
          </td>
        </tr>
      </table>
    """

    subject = f"🎉 Welcome to Mini Assistant {plan_display}!"
    html    = _shell(content, FRONTEND_URL, "Start Building")
    return subject, html


def _topup_html(name: str, credits_added: int, new_balance: int) -> tuple[str, str]:
    first = name.split()[0] if name else "there"

    content = f"""
      <h1 style="margin:0 0 8px;font-size:26px;font-weight:800;color:#ffffff;
                 letter-spacing:-0.5px;text-align:center;">
        Credits Added! ⚡
      </h1>
      <p style="margin:0 0 22px;font-size:14px;color:#94a3b8;
                line-height:1.7;text-align:center;">
        Hey {first}, your credit top-up is live and ready to use.
      </p>

      <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
             style="background:rgba(245,158,11,0.08);
                    border:1px solid rgba(245,158,11,0.25);
                    border-radius:14px;padding:22px;margin-bottom:18px;
                    text-align:center;">
        <tr><td>
          <p style="margin:0;font-size:44px;font-weight:900;color:#f59e0b;
                    letter-spacing:-1px;">
            +{credits_added:,}
          </p>
          <p style="margin:4px 0 0;font-size:12px;color:#94a3b8;font-weight:600;">
            credits added instantly
          </p>
        </td></tr>
      </table>

      <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
             style="background:rgba(255,255,255,0.03);
                    border:1px solid rgba(255,255,255,0.06);
                    border-radius:12px;padding:14px 18px;">
        <tr><td>
          <p style="margin:0;font-size:13px;color:#94a3b8;">
            New balance:
            <strong style="color:#ffffff;">{new_balance:,} credits</strong>
          </p>
          <p style="margin:4px 0 0;font-size:11px;color:#475569;">
            Top-up credits never expire and stack on your monthly plan credits.
          </p>
        </td></tr>
      </table>
    """

    subject = f"⚡ {credits_added:,} credits added to your account"
    html    = _shell(content, FRONTEND_URL, "Start Building")
    return subject, html


# ---------------------------------------------------------------------------
# Low-level Resend send
# ---------------------------------------------------------------------------

async def _send(
    to_email: str,
    to_name: str,
    subject: str,
    html_body: str,
    *,
    user_id: str = "",
    email_type: str = "upgrade",
    db=None,
) -> bool:
    if not resend.api_key:
        log.warning("email_sender: RESEND_API_KEY not set — skipping (to=%s)", to_email)
        return False

    params: resend.Emails.SendParams = {
        "from":    SENDER,
        "to":      [to_email],
        "subject": subject,
        "html":    html_body,
    }

    # Use shared logger with retry when DB is available
    if db is not None:
        try:
            from email_logger import send_with_log   # noqa: PLC0415
            return await send_with_log(
                db=db,
                user_id=user_id or to_email,
                email=to_email,
                email_type=email_type,
                send_fn=resend.Emails.send,
                params=params,
                subject=subject,
            )
        except Exception as exc:
            log.warning("email_logger unavailable, sending directly: %s", exc)

    # Fallback: direct send, no logging
    try:
        resp = resend.Emails.send(params)
        log.info("Email sent via Resend: to=%s subject=%s id=%s",
                 to_email, subject, resp.get("id"))
        return True
    except Exception as exc:
        log.error("Resend send failed (to=%s subject=%s): %s", to_email, subject, exc)
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def send_welcome_email(
    to_email: str,
    to_name: str,
    plan: str,
    credits: int,
    *,
    user_id: str = "",
    db=None,
) -> bool:
    """Send a plan upgrade welcome email. Non-fatal."""
    try:
        subject, html = _welcome_html(to_name, plan, credits)
        return await _send(
            to_email, to_name, subject, html,
            user_id=user_id or to_email,
            email_type="upgrade",
            db=db,
        )
    except Exception as exc:
        log.error("send_welcome_email failed: %s", exc)
        return False


async def send_topup_email(
    to_email: str,
    to_name: str,
    credits_added: int,
    new_balance: int,
    *,
    user_id: str = "",
    db=None,
) -> bool:
    """Send a top-up confirmation email. Non-fatal."""
    try:
        subject, html = _topup_html(to_name, credits_added, new_balance)
        return await _send(
            to_email, to_name, subject, html,
            user_id=user_id or to_email,
            email_type="topup",
            db=db,
        )
    except Exception as exc:
        log.error("send_topup_email failed: %s", exc)
        return False


def _referral_signup_html(referrer_name: str, sub_bonus: int) -> tuple[str, str]:
    subject = "🔥 Someone joined using your referral link!"
    content = f"""
      <h1 style="margin:0 0 8px;font-size:22px;font-weight:800;color:#ffffff;letter-spacing:-0.5px;">
        Someone joined with your link!
      </h1>
      <p style="margin:0 0 24px;font-size:15px;color:#94a3b8;line-height:1.6;">
        Hey {referrer_name}, a new user just signed up using your referral link.
      </p>

      <div style="background:#0d1117;border:1px solid rgba(16,185,129,0.25);border-radius:14px;padding:20px 24px;margin-bottom:24px;">
        <p style="margin:0 0 10px;font-size:13px;font-weight:600;color:#94a3b8;text-transform:uppercase;letter-spacing:1px;">
          What happens next
        </p>
        <div style="display:flex;align-items:flex-start;gap:12px;margin-bottom:12px;">
          <span style="font-size:18px;">⏳</span>
          <div>
            <p style="margin:0;font-size:14px;font-weight:600;color:#e2e8f0;">Pending reward</p>
            <p style="margin:4px 0 0;font-size:13px;color:#64748b;line-height:1.5;">
              Your friend just signed up. Once they subscribe to a paid plan, you'll both earn <strong style="color:#10b981;">+{sub_bonus} credits</strong>.
            </p>
          </div>
        </div>
        <div style="display:flex;align-items:flex-start;gap:12px;">
          <span style="font-size:18px;">🎁</span>
          <div>
            <p style="margin:0;font-size:14px;font-weight:600;color:#e2e8f0;">Max reward: 150 credits</p>
            <p style="margin:4px 0 0;font-size:13px;color:#64748b;line-height:1.5;">
              Refer up to 3 friends who subscribe and earn up to 150 bonus credits total.
            </p>
          </div>
        </div>
      </div>

      <p style="margin:0 0 24px;font-size:14px;color:#94a3b8;line-height:1.6;text-align:center;">
        Keep sharing your referral link to maximise your rewards! 🚀
      </p>
    """
    html = _shell(content, FRONTEND_URL, "View my dashboard")
    return subject, html


async def send_referral_signup_email(
    to_email: str,
    to_name: str,
    sub_bonus: int = 50,
    *,
    user_id: str = "",
    db=None,
) -> bool:
    """Notify referrer that someone signed up with their link. Non-fatal."""
    try:
        subject, html = _referral_signup_html(to_name, sub_bonus)
        return await _send(
            to_email, to_name, subject, html,
            user_id=user_id or to_email,
            email_type="referral_signup",
            db=db,
        )
    except Exception as exc:
        log.error("send_referral_signup_email failed: %s", exc)
        return False
