"""
email_service.py
Resend-based signup welcome email for Mini Assistant AI.
Called on register / Google OAuth — runs in a daemon thread (sync wrapper).
"""

import asyncio
import logging
import os

import resend

resend.api_key = os.environ.get("RESEND_API_KEY", "")

log = logging.getLogger(__name__)

SENDER      = "Mini Assistant AI <onboarding@resend.dev>"
FRONTEND    = os.environ.get("FRONTEND_URL", "https://miniassistantai.com")
PRICING_URL = f"{FRONTEND}/pricing"
LOGO_URL    = "https://miniassistantai.com/logo.png"


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

def _build_html(name: str) -> str:
    first = name.split()[0] if name else "there"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Welcome to Mini Assistant AI</title>
</head>
<body style="margin:0;padding:0;background-color:#0d0d12;font-family:Inter,system-ui,-apple-system,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
         style="background-color:#0d0d12;min-height:100vh;">
    <tr>
      <td align="center" style="padding:48px 16px;">
        <table width="100%" style="max-width:520px;" cellpadding="0" cellspacing="0" role="presentation">

          <!-- Logo -->
          <tr>
            <td align="center" style="padding-bottom:32px;">
              <img src="{LOGO_URL}" width="120" alt="Mini Assistant AI"
                   style="display:block;border:0;outline:none;text-decoration:none;" />
            </td>
          </tr>

          <!-- Card -->
          <tr>
            <td style="background:#111118;border:1px solid rgba(255,255,255,0.08);
                       border-radius:20px;padding:40px 36px;">

              <!-- Title -->
              <h1 style="margin:0 0 8px;font-size:28px;font-weight:800;color:#ffffff;
                         letter-spacing:-0.5px;text-align:center;">
                Welcome, {first}! 🚀
              </h1>

              <!-- Subtitle -->
              <p style="margin:0 0 24px;font-size:15px;color:#94a3b8;
                        line-height:1.7;text-align:center;">
                Your Mini Assistant AI account is ready.<br />
                Build apps, chat with AI, generate images, and ship — all in one place.
              </p>

              <!-- Feature highlights -->
              <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
                     style="margin-bottom:28px;">
                <tr>
                  <td style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);
                             border-radius:14px;padding:20px 24px;">
                    <p style="margin:0 0 12px;font-size:11px;font-weight:700;color:#475569;
                              text-transform:uppercase;letter-spacing:1.5px;">
                      What you can do
                    </p>
                    <table width="100%" cellpadding="0" cellspacing="0" role="presentation">
                      <tr>
                        <td style="padding:5px 0;font-size:13px;color:#cbd5e1;">
                          <span style="color:#06b6d4;margin-right:10px;">✓</span>Chat with Claude AI
                        </td>
                      </tr>
                      <tr>
                        <td style="padding:5px 0;font-size:13px;color:#cbd5e1;">
                          <span style="color:#06b6d4;margin-right:10px;">✓</span>Generate images instantly
                        </td>
                      </tr>
                      <tr>
                        <td style="padding:5px 0;font-size:13px;color:#cbd5e1;">
                          <span style="color:#06b6d4;margin-right:10px;">✓</span>Build & deploy full apps
                        </td>
                      </tr>
                      <tr>
                        <td style="padding:5px 0;font-size:13px;color:#cbd5e1;">
                          <span style="color:#06b6d4;margin-right:10px;">✓</span>Push to GitHub in one click
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>

              <!-- Credits callout -->
              <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
                     style="margin-bottom:28px;">
                <tr>
                  <td style="background:rgba(6,182,212,0.08);border:1px solid rgba(6,182,212,0.25);
                             border-radius:12px;padding:14px 18px;">
                    <p style="margin:0;font-size:13px;color:#ffffff;font-weight:700;">
                      ⚡ You have 10 free credits to start
                    </p>
                    <p style="margin:4px 0 0;font-size:11px;color:#64748b;">
                      1 chat = 1 credit · 1 image = 3 credits. Upgrade for up to 10,000/month.
                    </p>
                  </td>
                </tr>
              </table>

              <!-- CTA button -->
              <table width="100%" cellpadding="0" cellspacing="0" role="presentation">
                <tr>
                  <td align="center">
                    <a href="{PRICING_URL}"
                       style="display:inline-block;background:linear-gradient(135deg,#06b6d4,#7c3aed);
                              color:#ffffff;font-size:15px;font-weight:700;text-decoration:none;
                              padding:14px 36px;border-radius:12px;letter-spacing:0.2px;">
                      View Plans &amp; Upgrade →
                    </a>
                  </td>
                </tr>
              </table>

            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td align="center" style="padding-top:24px;">
              <p style="margin:0 0 6px;font-size:12px;color:#334155;">
                Mini Assistant AI ·
                <a href="{FRONTEND}" style="color:#06b6d4;text-decoration:none;">
                  miniassistantai.com
                </a>
              </p>
              <p style="margin:0;font-size:11px;color:#1e293b;">
                You're receiving this because you created an account.
                Questions? Reply to this email.
              </p>
              <!-- Stamp -->
              <table width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;margin-top:20px;">
                <tr><td>
                  <hr style="border:none;border-top:1px solid #1e2030;margin:0 0 14px;" />
                  <p style="margin:0;font-size:12px;color:#888888;text-align:center;line-height:1.6;">
                    Powered by
                    <a href="{FRONTEND}" style="color:#888888;text-decoration:none;font-weight:600;">
                      Mini Assistant AI
                    </a>
                  </p>
                  <p style="margin:4px 0 0;font-size:11px;color:#555555;text-align:center;">
                    Build apps, chat with AI, ship faster.
                  </p>
                </td></tr>
              </table>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------

def send_welcome_email(user_email: str, name: str, user_id: str = "") -> None:
    """
    Send a signup welcome email via Resend.
    Designed to be called in a background thread — never raises.
    Logs the send attempt to email_logs via email_logger.
    """
    if not resend.api_key:
        log.warning("send_welcome_email: RESEND_API_KEY not set — skipping")
        return

    subject = "Welcome to Mini Assistant AI 🚀"
    params: resend.Emails.SendParams = {
        "from":    SENDER,
        "to":      [user_email],
        "subject": subject,
        "html":    _build_html(name),
    }

    # Try to get DB and use the shared logger with retry
    try:
        import server as _srv  # noqa: PLC0415
        from email_logger import send_with_log  # noqa: PLC0415

        async def _async_send():
            return await send_with_log(
                db=_srv.db,
                user_id=user_id or user_email,
                email=user_email,
                email_type="welcome",
                send_fn=resend.Emails.send,
                params=params,
                subject=subject,
            )

        # Run in the current thread's event loop or create a new one
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(_async_send(), loop)
            else:
                loop.run_until_complete(_async_send())
        except RuntimeError:
            asyncio.run(_async_send())

    except Exception as exc:
        # Fallback: send directly without logging
        log.warning("email_logger unavailable, sending directly: %s", exc)
        try:
            response = resend.Emails.send(params)
            log.info("Welcome email sent to %s (id=%s)", user_email, response.get("id"))
        except Exception as send_exc:
            log.error("send_welcome_email failed for %s: %s", user_email, send_exc)
