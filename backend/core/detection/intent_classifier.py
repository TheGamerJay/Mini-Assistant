"""
detection/intent_classifier.py — CEO-level intent classifier.

Maps any user message to one of 10 CEO intents.
These are coarser than phase1's 13 intents — CEO cares about MODULE selection,
not execution detail. Execution detail is phase1's job.

CEO intents:
  general_chat      — conversation, explanation, Q&A
  task_assist       — resume, cover letter, professional email, follow-up
  campaign_lab      — ad, campaign, promo, hook, CTA, marketing
  web_lookup        — current info, news, live data, external search
  builder           — build app, create dashboard, add feature, backend
  image_generate    — generate/draw/create a visual
  image_edit        — modify/edit an attached image
  debug             — fix error, debug code, trace failure, patch system
  image_analyze     — analyze/describe/validate an image or UI screenshot
  execute           — apply changes, run, deploy, write file (Hands module)

Rules:
- attachments alone do not trigger image_edit — must have an edit instruction
- attachments + "analyze/describe/check" → image_analyze
- mode_hint from UI is passed in but ignored for intent — CEO decides independently
- returns (primary_intent, secondary_intent | None, confidence 0.0–1.0)
- existing phase1/intent_planner.py handles execution-level detail separately
"""

from __future__ import annotations

import re
from typing import Optional

# ---------------------------------------------------------------------------
# Pattern sets — ordered by priority (checked top → bottom, first match wins
# for primary; all matches considered for secondary)
# ---------------------------------------------------------------------------

_TASK_ASSIST = re.compile(
    r"\b(resume|cv|cover letter|cover_letter|job application|apply for|applying for|"
    r"follow.?up|followup|follow up email|linkedin message|linkedin outreach|"
    r"professional email|cold email|networking email|thank you email|"
    r"interview prep|interview question|salary negotiation|job offer|"
    r"reference letter|recommendation letter|portfolio|bio|personal statement)\b",
    re.IGNORECASE,
)

_CAMPAIGN_LAB = re.compile(
    r"\b(ad copy|ad campaign|promo|promotion|marketing|advertisement|"
    r"hook|cta|call to action|call-to-action|audience|target audience|"
    r"brand voice|tagline|headline copy|product launch|campaign brief|"
    r"email campaign|social media post|instagram caption|facebook ad|"
    r"google ad|tiktok script|youtube script|landing page copy)\b",
    re.IGNORECASE,
)

_WEB_LOOKUP = re.compile(
    r"\b(latest|current|right now|today|live|breaking|recent|news|"
    r"what('s| is) happening|search for|look up|look it up|find out|"
    r"check online|check the web|real.?time|stock price|weather|"
    r"sports score|upcoming events|release date|what came out)\b",
    re.IGNORECASE,
)

_BUILDER = re.compile(
    r"\b(build (me |us )?(an? |a |the )?(app|application|website|web app|dashboard|"
    r"calculator|todo|todo app|quiz|game|tool|widget|landing page|portfolio site)|"
    r"make (me |us )?(an? |a |the )?(app|website|dashboard|tool|calculator)|"
    r"create (an? |a )?(app|application|website|dashboard|tool)|"
    r"add (a |an )?(backend|leaderboard|login|auth|database|feature|api)|"
    r"set up (a )?(backend|database|api|server|auth)|"
    r"scaffold|boilerplate|starter template|full.?stack|fullstack)\b",
    re.IGNORECASE,
)

_IMAGE_EDIT = re.compile(
    r"\b(edit|modify|change|adjust|recolor|replace|remove|enhance|improve|"
    r"make (it |him |her |them )?(darker|brighter|older|younger|angrier)|"
    r"add .{1,40} to (the )?(image|photo|picture)|"
    r"remove .{1,40} from (the )?(image|photo|picture)|"
    r"uncrop|extend|inpaint|mask|retouch)\b",
    re.IGNORECASE,
)

_IMAGE_GEN = re.compile(
    r"\b(generate|create|draw|paint|render|make|produce|sketch|illustrate|"
    r"visualize|imagine|design)\b.{0,60}"
    r"\b(image|picture|photo|artwork|art|illustration|logo|icon|wallpaper|"
    r"poster|banner|thumbnail|avatar|portrait|scene|landscape)\b",
    re.IGNORECASE,
)

_DEBUG = re.compile(
    r"\b(debug|fix (the |this |my )?(bug|error|issue|code|crash|problem)|"
    r"why (is|does|isn.t|doesn.t|won.t|can.t)|not working|broken|crashed|"
    r"error (in|on|at|with)|exception|traceback|stack trace|log (shows|says)|"
    r"patch|repair|diagnose|troubleshoot|something.s wrong|wrong output)\b",
    re.IGNORECASE,
)

_IMAGE_ANALYZE = re.compile(
    r"\b(analyze|analyse|describe|what.s in|what is in|what do you see|"
    r"look at (this|the) (image|screenshot|photo|picture|ui|design)|"
    r"check (this|the) (image|screenshot|ui|design)|"
    r"validate (the )?(ui|design|layout|image)|review (the )?(design|ui|layout)|"
    r"what does (this|the) (image|screenshot) (show|contain|mean))\b",
    re.IGNORECASE,
)

_EXECUTE = re.compile(
    r"\b(apply (the |these |those )?(changes|fix|patch|code)|"
    r"write (it |the changes |this )?(to (the |a )?file|to disk)|"
    r"deploy|run (the |this )?(script|command|code)|execute (it|this|the)|"
    r"make (it|the change) happen|actually do (it|this)|go ahead (and )?do)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Full-system keywords (used by complexity_detector, exposed here too)
# ---------------------------------------------------------------------------

_FULL_SYSTEM_KW = re.compile(
    r"\b(global leaderboard|global score|global users|"
    r"login|sign.?in|sign.?up|authentication|auth system|"
    r"database|db|sql|mongodb|postgres|mysql|firebase|supabase|"
    r"save (data|progress|scores|state)|persist|sync|realtime|real.?time|"
    r"api|rest api|graphql|backend( server)?|admin panel|"
    r"user account|user profile|multi.?player|multiplayer|"
    r"production (code|app|system|build|ready))\b",
    re.IGNORECASE,
)

# Verbs that substitute for explicit "build/make/create" when paired with a
# full-system object — catches "write me a login system", "paste the code for
# a backend", "output the full backend files", "give me the implementation", etc.
#
# Pattern: verb + up to 25 chars of filler (articles, modifiers) + system noun.
# This lets "the full", "me the complete", "us the entire" etc. all pass through
# without enumerating every combination.
_BUILD_ALIAS_VERBS = re.compile(
    r"\b(write\b|paste\b|output\b|give\b|provide\b|show me\b|(?:i|we)\s+need\b)"
    r".{0,30}"
    r"\b(code|files?|implementation|system|app|application|"
    r"backend|service|module|solution|codebase|source)\b",
    re.IGNORECASE,
)

# Fullness modifiers — "whole", "entire", "all", "production" etc.
# Used as a secondary signal alongside _BUILD_ALIAS_VERBS when _FULL_SYSTEM_KW
# doesn't match (e.g. "write out the whole app here").
_FULLNESS_MODIFIER = re.compile(
    r"\b(whole|entire|complete|full|all|production|production.?ready|"
    r"full.?stack|end.?to.?end|working)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

def detect_intent(
    message: str,
    attachments: list,
) -> tuple[str, Optional[str], float]:
    """
    Returns:
        (primary_intent, secondary_intent | None, confidence)

    primary_intent is one of:
        general_chat | task_assist | campaign_lab | web_lookup |
        builder | image_generate | image_edit
    """
    msg = message.strip()
    has_attachment = bool(attachments)

    # Score each intent
    scores: dict[str, float] = {}

    if _TASK_ASSIST.search(msg):
        scores["task_assist"] = _score(_TASK_ASSIST, msg, base=0.85)

    if _CAMPAIGN_LAB.search(msg):
        scores["campaign_lab"] = _score(_CAMPAIGN_LAB, msg, base=0.85)

    if _WEB_LOOKUP.search(msg):
        scores["web_lookup"] = _score(_WEB_LOOKUP, msg, base=0.80)

    if _BUILDER.search(msg):
        scores["builder"] = _score(_BUILDER, msg, base=0.90)

    # Image edit requires an attachment AND an edit verb
    if has_attachment and _IMAGE_EDIT.search(msg):
        scores["image_edit"] = _score(_IMAGE_EDIT, msg, base=0.92)

    if _IMAGE_GEN.search(msg):
        scores["image_generate"] = _score(_IMAGE_GEN, msg, base=0.88)

    if _DEBUG.search(msg):
        scores["debug"] = _score(_DEBUG, msg, base=0.87)

    # image_analyze: attachment with analyze/describe verb, or explicit "look at this image"
    if _IMAGE_ANALYZE.search(msg) or (has_attachment and not _IMAGE_EDIT.search(msg) and
                                       re.search(r"\b(analyze|describe|check|review|validate|what)\b", msg, re.IGNORECASE)):
        scores["image_analyze"] = _score(_IMAGE_ANALYZE, msg, base=0.85)

    if _EXECUTE.search(msg):
        scores["execute"] = _score(_EXECUTE, msg, base=0.83)

    # Fallback A: alias verb + full-system keyword
    # "write me a login system with database", "paste the code for a backend"
    if "builder" not in scores and _BUILD_ALIAS_VERBS.search(msg) and _FULL_SYSTEM_KW.search(msg):
        scores["builder"] = 0.78

    # Fallback B: alias verb + fullness modifier (no explicit system keyword)
    # "write out the whole app here", "output the complete files", "paste the entire codebase"
    if "builder" not in scores and _BUILD_ALIAS_VERBS.search(msg) and _FULLNESS_MODIFIER.search(msg):
        scores["builder"] = 0.72

    if not scores:
        return "general_chat", None, 0.60

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    primary, primary_score = ranked[0]

    # Secondary: second-highest if score is meaningful
    secondary = None
    if len(ranked) >= 2 and ranked[1][1] >= 0.55:
        secondary = ranked[1][0]

    return primary, secondary, round(primary_score, 3)


def _score(pattern: re.Pattern, text: str, base: float) -> float:
    """Score based on number of pattern matches — capped at 1.0."""
    hits = pattern.findall(text)
    return min(base + len(hits) * 0.03, 1.0)
