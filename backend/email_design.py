"""
email_design.py
Reusable email design system for Mini Assistant AI — Phase 2.

All components return dark-themed HTML strings suitable for email clients.
No external CSS or images required.
"""

import os

FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://miniassistantai.com")
SENDER       = "Mini Assistant AI <onboarding@resend.dev>"
PRICING_URL  = f"{FRONTEND_URL}/pricing"
BILLING_URL  = f"{FRONTEND_URL}/dashboard"


# ---------------------------------------------------------------------------
# stamp
# ---------------------------------------------------------------------------

def stamp() -> str:
    """Footer 'Powered by Mini Assistant AI' block with divider."""
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


# ---------------------------------------------------------------------------
# logo_wordmark
# ---------------------------------------------------------------------------

def logo_wordmark() -> str:
    """Table row with gradient box + wordmark text."""
    return """
<tr><td align="center" style="padding-bottom:28px;">
  <table cellpadding="0" cellspacing="0" role="presentation">
    <tr>
      <td style="vertical-align:middle;padding-right:10px;">
        <div style="display:inline-block;width:32px;height:32px;border-radius:8px;
                    background:linear-gradient(135deg,#06b6d4,#7c3aed);
                    line-height:32px;font-size:0;">&nbsp;</div>
      </td>
      <td style="vertical-align:middle;">
        <span style="font-size:17px;font-weight:700;color:#ffffff;letter-spacing:-0.4px;
                     font-family:Inter,system-ui,-apple-system,sans-serif;">
          Mini Assistant AI
        </span>
      </td>
    </tr>
  </table>
</td></tr>"""


# ---------------------------------------------------------------------------
# header
# ---------------------------------------------------------------------------

def header(title: str, subtitle: str = "") -> str:
    """h1 + optional subtitle paragraph."""
    sub_html = ""
    if subtitle:
        sub_html = f"""
    <p style="margin:0 0 22px;font-size:14px;color:#94a3b8;
              line-height:1.7;text-align:center;">
      {subtitle}
    </p>"""
    return f"""
  <h1 style="margin:0 0 8px;font-size:26px;font-weight:800;color:#ffffff;
             letter-spacing:-0.5px;text-align:center;
             font-family:Inter,system-ui,-apple-system,sans-serif;">
    {title}
  </h1>{sub_html}"""


# ---------------------------------------------------------------------------
# feature_list
# ---------------------------------------------------------------------------

def feature_list(
    items: list,
    check_color: str = "#06b6d4",
    label: str = "",
) -> str:
    """Bordered table with checkmarks."""
    label_row = ""
    if label:
        label_row = f"""
    <tr><td style="padding-bottom:10px;font-size:11px;font-weight:700;
                   color:#475569;text-transform:uppercase;letter-spacing:1.5px;">
      {label}
    </td></tr>"""

    item_rows = "".join(
        f"""
    <tr><td style="padding:5px 0;font-size:13px;color:#cbd5e1;">
      <span style="color:{check_color};margin-right:10px;">&#10003;</span>{item}
    </td></tr>"""
        for item in items
    )

    return f"""
  <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
         style="background:rgba(255,255,255,0.03);
                border:1px solid rgba(255,255,255,0.06);
                border-radius:14px;padding:18px 22px;margin-bottom:18px;">
    {label_row}{item_rows}
  </table>"""


# ---------------------------------------------------------------------------
# callout_box
# ---------------------------------------------------------------------------

def callout_box(
    icon: str,
    title: str,
    body: str,
    bg_rgba: str = "rgba(6,182,212,0.08)",
    border_rgba: str = "rgba(6,182,212,0.25)",
) -> str:
    """Icon + text callout box."""
    return f"""
  <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
         style="background:{bg_rgba};border:1px solid {border_rgba};
                border-radius:12px;padding:14px 18px;margin-bottom:18px;">
    <tr>
      <td style="font-size:20px;width:32px;vertical-align:top;padding-top:2px;">{icon}</td>
      <td style="padding-left:10px;vertical-align:top;">
        <p style="margin:0;font-size:13px;font-weight:700;color:#ffffff;
                  font-family:Inter,system-ui,-apple-system,sans-serif;">
          {title}
        </p>
        <p style="margin:3px 0 0;font-size:11px;color:#64748b;
                  font-family:Inter,system-ui,-apple-system,sans-serif;">
          {body}
        </p>
      </td>
    </tr>
  </table>"""


# ---------------------------------------------------------------------------
# stat_large
# ---------------------------------------------------------------------------

def stat_large(value: str, label: str, color: str = "#f59e0b") -> str:
    """Large centered number/stat block."""
    return f"""
  <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
         style="background:rgba(245,158,11,0.08);
                border:1px solid rgba(245,158,11,0.25);
                border-radius:14px;padding:22px;margin-bottom:18px;
                text-align:center;">
    <tr><td>
      <p style="margin:0;font-size:44px;font-weight:900;color:{color};
                letter-spacing:-1px;font-family:Inter,system-ui,-apple-system,sans-serif;">
        {value}
      </p>
      <p style="margin:4px 0 0;font-size:12px;color:#94a3b8;font-weight:600;
                font-family:Inter,system-ui,-apple-system,sans-serif;">
        {label}
      </p>
    </td></tr>
  </table>"""


# ---------------------------------------------------------------------------
# credit_bar
# ---------------------------------------------------------------------------

def credit_bar(
    current: int,
    total: int,
    bar_color: str = "#f59e0b",
) -> str:
    """Progress bar with percentage showing remaining credits."""
    pct       = max(0, round(current / total * 100)) if total > 0 else 0
    bar_width = max(2, pct)
    return f"""
  <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
         style="background:rgba(245,158,11,0.08);
                border:1px solid rgba(245,158,11,0.30);
                border-radius:14px;padding:20px 22px;margin-bottom:18px;">
    <tr><td>
      <p style="margin:0 0 10px;font-size:13px;color:#94a3b8;
                font-family:Inter,system-ui,-apple-system,sans-serif;">
        Credits remaining:
        <strong style="color:{bar_color};font-size:16px;"> {current:,}</strong>
        <span style="color:#64748b;font-size:11px;"> / {total:,}</span>
      </p>
      <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
             style="background:#1e2030;border-radius:99px;height:8px;overflow:hidden;">
        <tr>
          <td width="{bar_width}%" style="background:{bar_color};height:8px;
              border-radius:99px;line-height:8px;font-size:0;">&nbsp;</td>
          <td></td>
        </tr>
      </table>
      <p style="margin:8px 0 0;font-size:11px;color:#64748b;
                font-family:Inter,system-ui,-apple-system,sans-serif;">
        {pct}% remaining &middot; 1 chat = 1 credit &middot; 1 image = 3 credits
      </p>
    </td></tr>
  </table>"""


# ---------------------------------------------------------------------------
# info_box
# ---------------------------------------------------------------------------

def info_box(body: str, detail: str = "") -> str:
    """Subtle info block with optional detail line."""
    detail_html = ""
    if detail:
        detail_html = f"""
        <p style="margin:4px 0 0;font-size:11px;color:#475569;
                  font-family:Inter,system-ui,-apple-system,sans-serif;">
          {detail}
        </p>"""
    return f"""
  <table width="100%" cellpadding="0" cellspacing="0" role="presentation"
         style="background:rgba(255,255,255,0.03);
                border:1px solid rgba(255,255,255,0.06);
                border-radius:12px;padding:14px 18px;margin-bottom:18px;">
    <tr><td>
      <p style="margin:0;font-size:13px;color:#94a3b8;
                font-family:Inter,system-ui,-apple-system,sans-serif;">
        {body}
      </p>{detail_html}
    </td></tr>
  </table>"""


# ---------------------------------------------------------------------------
# shell
# ---------------------------------------------------------------------------

def shell(
    content: str,
    cta_url: str = "",
    cta_label: str = "",
    footer_note: str = "",
) -> str:
    """
    Complete email HTML layout.
    Includes logo_wordmark(), dark bg, card, optional CTA button,
    footer with site link + footer_note + stamp().
    Mobile responsive max-width:520px.
    """
    cta_block = ""
    if cta_url and cta_label:
        cta_block = f"""
        <!-- CTA -->
        <table width="100%" cellpadding="0" cellspacing="0"
               role="presentation" style="padding-top:28px;">
          <tr><td align="center">
            <a href="{cta_url}"
               style="display:inline-block;
                      background:linear-gradient(135deg,#06b6d4,#7c3aed);
                      color:#ffffff;font-size:14px;font-weight:700;
                      text-decoration:none;padding:14px 32px;
                      border-radius:12px;letter-spacing:0.2px;
                      font-family:Inter,system-ui,-apple-system,sans-serif;">
              {cta_label} &#8594;
            </a>
          </td></tr>
        </table>"""

    note_html = ""
    if footer_note:
        note_html = f"""
          <p style="margin:6px 0 0;font-size:10px;color:#334155;text-align:center;
                    font-family:Inter,system-ui,-apple-system,sans-serif;">
            {footer_note}
          </p>"""

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

        {logo_wordmark()}

        <!-- Card -->
        <tr><td style="background:#111118;border:1px solid rgba(255,255,255,0.08);
                       border-radius:20px;padding:36px 32px;">

          {content}
          {cta_block}

        </td></tr>

        <!-- Footer -->
        <tr><td align="center" style="padding-top:20px;">
          <p style="margin:0;font-size:11px;color:#475569;text-align:center;
                    font-family:Inter,system-ui,-apple-system,sans-serif;">
            Mini Assistant AI &middot;
            <a href="{FRONTEND_URL}" style="color:#06b6d4;text-decoration:none;">
              miniassistantai.com
            </a>
          </p>
          {note_html}
          {stamp()}
        </td></tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""
