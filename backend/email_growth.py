"""
email_growth.py
Onboarding sequence management + A/B test analytics — Phase 4.

Exports:
  ONBOARDING_SEQUENCE  : dict mapping step index → email_type
  assign_variant()     : deterministic A/B variant from user_id + email_type
  get_sequence_step()  : find next unsent step for a user
  get_ab_analytics()   : aggregate A/B results from email_logs
  get_sequence_analytics() : funnel view for onboarding sequence
"""

import hashlib
import logging

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Onboarding sequence definition
# ---------------------------------------------------------------------------

ONBOARDING_SEQUENCE: dict = {
    0: "welcome",
    1: "followup_upgrade",
    2: "reminder",
}


# ---------------------------------------------------------------------------
# A/B variant assignment — deterministic, no DB required
# ---------------------------------------------------------------------------

def assign_variant(user_id: str, email_type: str) -> str:
    """
    Deterministic A/B variant assignment.
    Uses MD5 hash of '{user_id}:{email_type}' — same inputs always give same result.
    Returns "A" or "B".
    """
    digest = hashlib.md5(f"{user_id}:{email_type}".encode()).hexdigest()
    return "A" if int(digest, 16) % 2 == 0 else "B"


# ---------------------------------------------------------------------------
# Sequence step lookup
# ---------------------------------------------------------------------------

async def get_sequence_step(db, user_id: str) -> int:
    """
    Query email_logs to find the first missing step in ONBOARDING_SEQUENCE.
    Returns the step index to send next, or len(ONBOARDING_SEQUENCE) if complete.
    """
    try:
        sent_logs = await db["email_logs"].find(
            {
                "user_id":  user_id,
                "status":   "sent",
                "sequence": "onboarding",
            },
            {"sequence_step": 1},
        ).to_list(None)

        sent_steps = {doc.get("sequence_step") for doc in sent_logs if doc.get("sequence_step") is not None}

        for step in sorted(ONBOARDING_SEQUENCE.keys()):
            if step not in sent_steps:
                return step

        return len(ONBOARDING_SEQUENCE)

    except Exception as exc:
        log.warning("get_sequence_step: DB error (non-fatal): %s", exc)
        return 0


# ---------------------------------------------------------------------------
# A/B analytics aggregate
# ---------------------------------------------------------------------------

async def get_ab_analytics(db) -> dict:
    """
    Aggregate email_logs grouped by (email_type, variant, status).
    Returns nested dict: {email_type: {variant: {sent, failed, converted, conversion_rate}}}
    """
    try:
        pipeline = [
            {
                "$group": {
                    "_id": {
                        "email_type": "$email_type",
                        "variant":    "$variant",
                        "status":     "$status",
                    },
                    "count": {"$sum": 1},
                }
            },
        ]
        rows = await db["email_logs"].aggregate(pipeline).to_list(None)

        # Build intermediate structure: {email_type: {variant: {status: count}}}
        intermediate: dict = {}
        for row in rows:
            et  = row["_id"].get("email_type") or "unknown"
            var = row["_id"].get("variant") or "A"
            st  = row["_id"].get("status") or "unknown"
            cnt = row.get("count", 0)

            intermediate.setdefault(et, {}).setdefault(var, {})
            intermediate[et][var][st] = cnt

        # Fetch conversion counts grouped by (email_type, variant)
        conv_pipeline = [
            {"$match": {"converted": True}},
            {
                "$group": {
                    "_id": {
                        "email_type": "$email_type",
                        "variant":    "$variant",
                    },
                    "count": {"$sum": 1},
                }
            },
        ]
        conv_rows = await db["email_logs"].aggregate(conv_pipeline).to_list(None)
        conversions: dict = {}
        for row in conv_rows:
            et  = row["_id"].get("email_type") or "unknown"
            var = row["_id"].get("variant") or "A"
            conversions.setdefault(et, {})[var] = row.get("count", 0)

        # Build final result
        result: dict = {}
        for et, variants in intermediate.items():
            result[et] = {}
            for var, statuses in variants.items():
                sent      = statuses.get("sent", 0)
                failed    = statuses.get("failed", 0)
                converted = conversions.get(et, {}).get(var, 0)
                conv_rate = round(converted / sent * 100, 1) if sent > 0 else 0.0
                result[et][var] = {
                    "sent":            sent,
                    "failed":          failed,
                    "converted":       converted,
                    "conversion_rate": conv_rate,
                }

        return result

    except Exception as exc:
        log.warning("get_ab_analytics: DB error (non-fatal): %s", exc)
        return {}


# ---------------------------------------------------------------------------
# Sequence analytics
# ---------------------------------------------------------------------------

async def get_sequence_analytics(db) -> dict:
    """
    Aggregate email_logs where sequence="onboarding" and status="sent".
    Groups by sequence_step, returns funnel with conversion rates.
    """
    try:
        pipeline = [
            {"$match": {"sequence": "onboarding", "status": "sent"}},
            {
                "$group": {
                    "_id":   "$sequence_step",
                    "count": {"$sum": 1},
                    "email_type": {"$first": "$email_type"},
                }
            },
            {"$sort": {"_id": 1}},
        ]
        rows = await db["email_logs"].aggregate(pipeline).to_list(None)

        # Conversion counts per step
        conv_pipeline = [
            {"$match": {"sequence": "onboarding", "converted": True}},
            {
                "$group": {
                    "_id":   "$sequence_step",
                    "count": {"$sum": 1},
                }
            },
        ]
        conv_rows = await db["email_logs"].aggregate(conv_pipeline).to_list(None)
        conversions_by_step = {row["_id"]: row["count"] for row in conv_rows}

        steps = []
        for row in rows:
            step       = row["_id"]
            sent       = row.get("count", 0)
            email_type = row.get("email_type") or ONBOARDING_SEQUENCE.get(step, "unknown")
            converted  = conversions_by_step.get(step, 0)
            conv_rate  = round(converted / sent * 100, 1) if sent > 0 else 0.0
            steps.append({
                "step":            step,
                "email_type":      email_type,
                "sent":            sent,
                "converted":       converted,
                "conversion_rate": conv_rate,
            })

        return {
            "sequence": "onboarding",
            "steps":    steps,
        }

    except Exception as exc:
        log.warning("get_sequence_analytics: DB error (non-fatal): %s", exc)
        return {"sequence": "onboarding", "steps": []}
