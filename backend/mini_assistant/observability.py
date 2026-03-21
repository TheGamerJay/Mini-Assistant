"""
mini_assistant/observability.py
────────────────────────────────
Lightweight telemetry logger for the AI orchestra.

Appends one JSON line per brain call to logs/telemetry.jsonl.
Non-fatal: observability failures never break the main pipeline.

Ceiling architecture layer:
  • Records every brain call with model, latency, confidence, outcome
  • Enables the meta-brain to detect slow/weak/failing brains
  • Powers future observability dashboard and auto-routing improvements
"""
from __future__ import annotations

import json
import time
import logging
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_LOG_DIR  = Path(__file__).parent.parent / "image_system" / "logs"
_LOG_FILE = _LOG_DIR / "telemetry.jsonl"


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class BrainCall:
    """One record per brain invocation."""
    brain:      str          # vision | builder | reviewer | escalation | router | …
    model:      str          # exact model name
    task:       str          # short description of what was asked
    session_id: str  = ""
    mission_id: str  = ""
    latency_ms: float = 0.0
    confidence: float = -1.0   # -1 = not scored; 0–100 = scored
    outcome:    str  = "unknown"   # success | fail | partial | escalated | skipped
    tokens_out: int  = 0
    escalated:  bool = False
    notes:      str  = ""
    timestamp:  str  = field(
        default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    )


# ── Write ─────────────────────────────────────────────────────────────────────

def record(call: BrainCall) -> None:
    """Append a BrainCall to telemetry.jsonl. Never raises."""
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        with _LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(call)) + "\n")
    except Exception as exc:
        logger.debug("Observability write failed (non-fatal): %s", exc)


# ── Read / aggregate ──────────────────────────────────────────────────────────

def get_recent(n: int = 200) -> list[dict]:
    """Return the last N telemetry records."""
    try:
        if not _LOG_FILE.exists():
            return []
        lines = _LOG_FILE.read_text(encoding="utf-8").splitlines()
        return [json.loads(ln) for ln in lines[-n:] if ln.strip()]
    except Exception as exc:
        logger.debug("Observability read failed: %s", exc)
        return []


def summary_stats() -> dict:
    """Aggregate stats from the last 1 000 calls for the dashboard."""
    try:
        records = get_recent(1000)
        if not records:
            return {}
        brain_counts  = Counter(r["brain"]   for r in records)
        model_counts  = Counter(r["model"]   for r in records)
        outcomes      = Counter(r["outcome"] for r in records)
        avg_lat       = sum(r["latency_ms"] for r in records) / len(records)
        escalations   = sum(1 for r in records if r.get("escalated"))
        scored        = [r["confidence"] for r in records if r["confidence"] >= 0]
        avg_conf      = sum(scored) / len(scored) if scored else -1
        fail_brains   = Counter(
            r["brain"] for r in records if r["outcome"] == "fail"
        )
        return {
            "total_calls":      len(records),
            "brain_breakdown":  dict(brain_counts),
            "model_breakdown":  dict(model_counts),
            "outcome_breakdown": dict(outcomes),
            "avg_latency_ms":   round(avg_lat, 1),
            "escalation_count": escalations,
            "avg_confidence":   round(avg_conf, 1) if avg_conf >= 0 else None,
            "most_failing_brains": dict(fail_brains.most_common(5)),
        }
    except Exception as exc:
        logger.debug("Observability stats failed: %s", exc)
        return {}


# ── Timer helper ──────────────────────────────────────────────────────────────

class Timer:
    """Context manager that measures elapsed wall-clock time."""
    elapsed_ms: float = 0.0

    def __enter__(self) -> "Timer":
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, *_) -> None:
        self.elapsed_ms = (time.perf_counter() - self._t0) * 1000