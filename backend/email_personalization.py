"""
email_personalization.py
A/B subject selection + AI-powered subject personalization + tone system — Phase 3.

Exports:
  AI_ENABLED            : bool
  get_subject()         : static A/B subject lookup
  personalize_subject() : async AI-enhanced subject (falls back to static)
  select_tone()         : rule-based tone selector
  get_tone_snippets()   : (opener, closer) tuple for tone
"""

import logging
import os

log = logging.getLogger(__name__)

AI_ENABLED: bool = os.environ.get("EMAIL_AI_ENABLED", "false").lower() == "true"

# ---------------------------------------------------------------------------
# Static A/B subject variants
# ---------------------------------------------------------------------------

_SUBJECT_VARIANTS: dict = {
    "followup_upgrade": {
        "A": "Still thinking about upgrading? Here's what you're missing \U0001f680",
        "B": "Unlock 10\u00d7 more building power \u2014 upgrade today \U0001f513",
    },
    "low_credits": {
        "A": "\u26a1 You're running low on credits \u2014 top up to keep building",
        "B": "\U0001f6a8 Almost out of credits \u2014 don't let your momentum stop",
    },
    "payment_failed": {
        "A": "\u26a0\ufe0f Payment issue \u2014 please update your billing details",
        "B": "\u26a0\ufe0f Action required: keep your plan active",
    },
    "reminder": {
        "A": "One last nudge \u2014 have you tried upgrading? \U0001f4a1",
        "B": "Your free plan is holding you back \u2014 upgrade today \U0001f680",
    },
    "upgrade": {
        "A": "\U0001f389 You're on {plan}!",
        "B": "Welcome to {plan} \u2014 here's what's unlocked \U0001f389",
    },
    "topup": {
        "A": "\u26a1 {n} credits added to your account",
        "B": "\u26a1 Credits topped up \u2014 keep building!",
    },
    "welcome": {
        "A": "Welcome to Mini Assistant AI \U0001f680",
        "B": "Your AI assistant is ready \u2014 let's build something \U0001f6e0\ufe0f",
    },
}

# ---------------------------------------------------------------------------
# Tone openers / closers
# ---------------------------------------------------------------------------

_TONE_OPENERS: dict = {
    "urgency":      "Time is running out \u2014 act now to stay unblocked.",
    "friendly":     "Hope you're having a great day!",
    "motivational": "You're one step away from building something amazing.",
}

_TONE_CLOSERS: dict = {
    "urgency":      "Don't wait \u2014 sort this out now and get back to building.",
    "friendly":     "We're always here if you need anything. Happy building! \U0001f44b",
    "motivational": "Every great product started with a single click. Yours could be next. \U0001f680",
}


# ---------------------------------------------------------------------------
# select_tone
# ---------------------------------------------------------------------------

def select_tone(user: dict, email_type: str) -> str:
    """
    Rule-based tone selector.
    Returns one of: "urgency", "friendly", "motivational"
    """
    failure_count = user.get("payment_failure_count", 0) or 0
    plan          = (user.get("plan") or "free").lower()
    sub_credits   = user.get("subscription_credits", 0) or 0
    topup_credits = user.get("topup_credits", 0) or 0
    credits       = sub_credits + topup_credits

    if email_type == "payment_failed" or failure_count >= 2:
        return "urgency"

    if email_type == "low_credits" and credits < 5:
        return "urgency"

    if plan == "free" and email_type in ("followup_upgrade", "reminder"):
        return "motivational"

    return "friendly"


# ---------------------------------------------------------------------------
# get_subject
# ---------------------------------------------------------------------------

def get_subject(
    email_type: str,
    variant: str,
    user: dict | None = None,
) -> str:
    """
    Look up static A/B subject variant.
    Handles {plan} substitution for upgrade emails.
    Returns empty string if email_type not found.
    """
    type_variants = _SUBJECT_VARIANTS.get(email_type, {})
    subject = type_variants.get(variant, type_variants.get("A", ""))

    if "{plan}" in subject and user is not None:
        plan_display = (user.get("plan") or "Standard").capitalize()
        subject = subject.replace("{plan}", plan_display)
    elif "{plan}" in subject:
        subject = subject.replace("{plan}", "Standard")

    if "{n}" in subject and user is not None:
        # topup emails: n comes from params, fallback to generic
        subject = subject.replace("{n}", "Your")

    return subject


# ---------------------------------------------------------------------------
# personalize_subject
# ---------------------------------------------------------------------------

async def personalize_subject(
    email_type: str,
    variant: str,
    user: dict,
    static_fallback: str = "",
) -> str:
    """
    Return a subject line for the email.
    If AI_ENABLED=false: returns static_fallback or get_subject().
    If AI_ENABLED=true: uses Claude Haiku to generate an improved subject,
    falling back to static on any error.
    """
    fallback = static_fallback or get_subject(email_type, variant, user)

    if not AI_ENABLED:
        return fallback

    try:
        import anthropic  # noqa: PLC0415

        name    = (user.get("name") or "").split()[0] if user.get("name") else "there"
        plan    = (user.get("plan") or "free").lower()
        tone    = select_tone(user, email_type)

        prompt = (
            f"You are writing a transactional email subject line for Mini Assistant AI, "
            f"a SaaS tool for building apps with AI.\n"
            f"Email type: {email_type}\n"
            f"User first name: {name}\n"
            f"User plan: {plan}\n"
            f"Tone: {tone}\n"
            f"Base subject: {fallback}\n\n"
            f"Write one improved email subject line. "
            f"Keep it under 70 characters. "
            f"Make it compelling and specific. "
            f"Output only the subject line text, nothing else."
        )

        client = anthropic.AsyncAnthropic(timeout=5.0)
        message = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=80,
            messages=[{"role": "user", "content": prompt}],
        )
        generated = message.content[0].text.strip().strip('"').strip("'")
        if generated:
            return generated
        return fallback

    except Exception as exc:
        log.debug("personalize_subject: AI generation failed (non-fatal): %s", exc)
        return fallback


# ---------------------------------------------------------------------------
# get_tone_snippets
# ---------------------------------------------------------------------------

def get_tone_snippets(tone: str) -> tuple:
    """Return (opener, closer) strings for the given tone key."""
    opener = _TONE_OPENERS.get(tone, _TONE_OPENERS["friendly"])
    closer = _TONE_CLOSERS.get(tone, _TONE_CLOSERS["friendly"])
    return opener, closer
