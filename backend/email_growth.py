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
import os
import time

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# A/B winner selection config
# ---------------------------------------------------------------------------

AB_MIN_SAMPLE        = int(os.environ.get("AB_MIN_SAMPLE", "50"))
AB_SIGNIFICANCE_PCT  = float(os.environ.get("AB_SIGNIFICANCE_PCT", "10.0"))

# Weight shift schedule for winner: 50 → 70 → 90 (capped — never 100% to keep learning)
_WEIGHT_SHIFTS: dict = {50: 70, 70: 90, 90: 90, 30: 10, 10: 10}

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

async def get_ab_weight(db, email_type: str) -> int:
    """
    Fetch the current traffic weight for variant A from email_ab_weights.
    Returns an int 0-100. Default 50 (equal split) if not set or on any error.
    """
    try:
        doc = await db["email_ab_weights"].find_one({"email_type": email_type})
        if doc and "weight_a" in doc:
            return max(0, min(100, int(doc["weight_a"])))
    except Exception as exc:
        log.debug("get_ab_weight: fallback to 50 for %s (%s)", email_type, exc)
    return 50


def assign_variant(user_id: str, email_type: str, weight_a: int = 50) -> str:
    """
    Weighted, deterministic A/B variant assignment.
    Maps MD5 hash position (0-99) against weight_a threshold.
    Same user_id + email_type always lands in the same position, so
    shifting weight_a progressively moves borderline users to the winner.
    Returns "A" or "B".
    """
    digest   = hashlib.md5(f"{user_id}:{email_type}".encode()).hexdigest()
    position = int(digest, 16) % 100   # uniform 0–99
    return "A" if position < weight_a else "B"


async def evaluate_ab_winners(db) -> None:
    """
    Compare A vs B conversion rates per email_type.
    If one variant outperforms by AB_SIGNIFICANCE_PCT with >= AB_MIN_SAMPLE each,
    shift traffic 50→70→90 toward the winner in email_ab_weights.
    Non-fatal — runs as part of the automation loop.
    """
    try:
        pipeline = [
            {"$match": {"variant": {"$in": ["A", "B"]}, "status": "sent"}},
            {"$group": {
                "_id":       {"email_type": "$email_type", "variant": "$variant"},
                "count":     {"$sum": 1},
                "converted": {"$sum": {"$cond": [{"$eq": ["$converted", True]}, 1, 0]}},
            }},
        ]
        rows = await db["email_logs"].aggregate(pipeline).to_list(None)

        # Build {email_type: {variant: {count, rate}}}
        stats: dict = {}
        for row in rows:
            et  = row["_id"]["email_type"]
            v   = row["_id"]["variant"]
            cnt = row["count"]
            conv = row["converted"]
            stats.setdefault(et, {})[v] = {
                "count": cnt,
                "rate":  conv / cnt if cnt else 0.0,
            }

        for email_type, variants in stats.items():
            a = variants.get("A")
            b = variants.get("B")
            if not a or not b:
                continue

            # Require minimum sample size in both arms
            if a["count"] < AB_MIN_SAMPLE or b["count"] < AB_MIN_SAMPLE:
                continue

            diff = abs(a["rate"] - b["rate"])
            if diff < (AB_SIGNIFICANCE_PCT / 100):
                continue   # not significant enough

            winner = "A" if a["rate"] >= b["rate"] else "B"

            # Get current weight
            current_doc = await db["email_ab_weights"].find_one({"email_type": email_type})
            cur_w_a = int(current_doc["weight_a"]) if current_doc else 50

            if winner == "A":
                new_w_a = _WEIGHT_SHIFTS.get(cur_w_a, cur_w_a)
            else:
                # Shift toward B = decrease weight_a
                mirrored = _WEIGHT_SHIFTS.get(100 - cur_w_a, 100 - cur_w_a)
                new_w_a  = 100 - mirrored

            if new_w_a == cur_w_a:
                continue   # already at maximum shift

            log.info(
                "email_growth: %s winner=%s (rate_A=%.1f%% rate_B=%.1f%% diff=%.1f%%) "
                "shifting weight_a %d→%d",
                email_type, winner,
                a["rate"] * 100, b["rate"] * 100, diff * 100,
                cur_w_a, new_w_a,
            )
            await db["email_ab_weights"].update_one(
                {"email_type": email_type},
                {"$set": {
                    "weight_a":    new_w_a,
                    "winner":      winner,
                    "diff_pct":    round(diff * 100, 2),
                    "rate_a":      round(a["rate"] * 100, 2),
                    "rate_b":      round(b["rate"] * 100, 2),
                    "sample_a":    a["count"],
                    "sample_b":    b["count"],
                    "evaluated_at": time.time(),
                }},
                upsert=True,
            )

    except Exception as exc:
        log.error("evaluate_ab_winners failed (non-fatal): %s", exc)


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


# ---------------------------------------------------------------------------
# Revenue analytics
# ---------------------------------------------------------------------------

async def get_revenue_analytics(db) -> dict:
    """
    Aggregate revenue_generated from converted email_logs.
    Returns revenue_by_email_type, revenue_by_variant, top/worst performers.
    """
    _empty = {
        "revenue_by_email_type": {},
        "revenue_by_variant":    {},
        "top_performing":        None,
        "worst_performing":      None,
        "ranked":                [],
        "total_revenue":         0.0,
    }
    try:
        pipeline = [
            {"$match": {"revenue_generated": {"$gt": 0}, "converted": True}},
            {"$group": {
                "_id": {"email_type": "$email_type", "variant": "$variant"},
                "total_revenue": {"$sum": "$revenue_generated"},
                "count":         {"$sum": 1},
                "avg_revenue":   {"$avg": "$revenue_generated"},
            }},
            {"$sort": {"total_revenue": -1}},
        ]
        rows = await db["email_logs"].aggregate(pipeline).to_list(None)
        if not rows:
            return _empty

        by_type:    dict = {}
        by_variant: dict = {}
        ranked:     list = []

        for row in rows:
            et      = row["_id"].get("email_type") or "unknown"
            variant = row["_id"].get("variant")
            rev     = round(row["total_revenue"], 2)
            count   = row["count"]
            avg     = round(row["avg_revenue"], 2)

            by_type[et] = round(by_type.get(et, 0) + rev, 2)

            if variant:
                key = f"{et}_{variant}"
                by_variant[key] = {"revenue": rev, "count": count, "avg_revenue": avg}

            ranked.append({
                "email_type": et,
                "variant":    variant,
                "revenue":    rev,
                "count":      count,
                "avg_revenue": avg,
            })

        total = round(sum(by_type.values()), 2)
        return {
            "revenue_by_email_type": by_type,
            "revenue_by_variant":    by_variant,
            "top_performing":        ranked[0]  if ranked else None,
            "worst_performing":      ranked[-1] if ranked else None,
            "ranked":                ranked,
            "total_revenue":         total,
        }

    except Exception as exc:
        log.error("get_revenue_analytics failed (non-fatal): %s", exc)
        return _empty


async def get_ab_weights_snapshot(db) -> dict:
    """Return current A/B weight config for all email types (admin view)."""
    try:
        docs = await db["email_ab_weights"].find({}, {"_id": 0}).to_list(None)
        return {d["email_type"]: d for d in docs if "email_type" in d}
    except Exception as exc:
        log.warning("get_ab_weights_snapshot failed (non-fatal): %s", exc)
        return {}
