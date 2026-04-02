"""
memory/task_assist_retrieval.py — Task-type-aware scope selector for task_assist.

CEO uses this to decide which TR memory keys to load based on what the user is
actually trying to do. Loading the full scope for every task wastes context —
this enforces the minimum necessary retrieval.

Task types and their required memory keys:
  cover_letter     → resume, skills, applications (latest)
  resume_update    → resume, user_profile
  follow_up        → applications, last_followup
  message          → message_history, tone_preferences
  job_application  → resume, user_profile, applications (past roles)
  general          → resume, user_profile (safe default)

Prioritization:
  - most recent entries
  - matching role/company
  - prefer exact matches
  - fallback to user profile

Rules:
  - do NOT load full history
  - do NOT fabricate missing memory (caller must surface this)
  - retrieve only what is needed for the detected task_type
"""

from __future__ import annotations

import re

# ── Task-type detection patterns ───────────────────────────────────────────────
_COVER_LETTER = re.compile(
    r"\b(cover letter|covering letter|letter of (interest|motivation|application))\b",
    re.IGNORECASE,
)
_RESUME_UPDATE = re.compile(
    r"\b(update (my |the )?(resume|cv)|improve (my |the )?(resume|cv)|"
    r"add to (my |the )?(resume|cv)|rewrite (my |the )?(resume|cv)|"
    r"edit (my |the )?(resume|cv)|fix (my |the )?(resume|cv))\b",
    re.IGNORECASE,
)
_FOLLOW_UP = re.compile(
    r"\b(follow.up|following up|check in|follow (on|with)|"
    r"heard back|any update|status (of |on )?my application)\b",
    re.IGNORECASE,
)
_MESSAGE = re.compile(
    r"\b(write (a |an )?(email|message|note|dm|text)|draft (a |an )?(email|message|note)|"
    r"compose|reply to|respond to|reach out)\b",
    re.IGNORECASE,
)
_JOB_APPLICATION = re.compile(
    r"\b(apply (to|for)|job application|applying for|submit (a |an )?application|"
    r"send (my )?(application|resume|cv))\b",
    re.IGNORECASE,
)

# ── Scope per task_type ────────────────────────────────────────────────────────
_TASK_SCOPES: dict[str, list[str]] = {
    "cover_letter":    ["resume", "skills", "applications"],
    "resume_update":   ["resume", "user_profile"],
    "follow_up":       ["applications", "last_followup"],
    "message":         ["message_history", "tone_preferences"],
    "job_application": ["resume", "user_profile", "applications"],
    "general":         ["resume", "user_profile"],
}


def detect_task_type(message: str) -> str:
    """
    Detect which task_assist task type the message represents.
    Returns one of: cover_letter, resume_update, follow_up, message, job_application, general.
    """
    if _COVER_LETTER.search(message):
        return "cover_letter"
    if _RESUME_UPDATE.search(message):
        return "resume_update"
    if _FOLLOW_UP.search(message):
        return "follow_up"
    if _JOB_APPLICATION.search(message):
        return "job_application"
    if _MESSAGE.search(message):
        return "message"
    return "general"


def get_scope(message: str) -> str:
    """
    Return a scope string for task_assist based on the message content.
    Format: "task_assist:key1,key2,..."

    CEO calls this during memory_decider to get the minimum required scope.
    """
    task_type = detect_task_type(message)
    keys = _TASK_SCOPES[task_type]
    return f"task_assist:{','.join(keys)}"


def get_required_keys(task_type: str) -> list[str]:
    """
    Return the required memory keys for a task_type.
    Used by clarification_engine to check if memory is present before proceeding.
    """
    return _TASK_SCOPES.get(task_type, _TASK_SCOPES["general"])
