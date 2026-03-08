"""
Standalone router test script.

Run with:
    python -m backend.image_system.tests.test_router
or from the image_system directory:
    python tests/test_router.py

Does NOT require ComfyUI. Only requires Ollama to be running with the
required models pulled. Falls back gracefully to keyword-only routing if
Ollama is unavailable.
"""

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Optional

# Make sure the package is importable when run directly
_ROOT = Path(__file__).parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backend.image_system.brains.router_brain import RouterBrain


# ---------------------------------------------------------------------------
# Test prompts
# ---------------------------------------------------------------------------

TEST_PROMPTS = [
    ("draw a shonen anime warrior with lightning aura", "image_generation", "anime", "anime_shonen"),
    ("create a romantic anime couple at sunset", "image_generation", "anime", "anime_shojo"),
    ("realistic DSLR portrait of a woman in natural lighting", "image_generation", "realistic", "realistic"),
    ("dark grim anime assassin in rain", "image_generation", "anime", "anime_seinen"),
    ("cute anime school girl in classroom", "image_generation", "anime", "anime_slice_of_life"),
    ("epic fantasy dragon over a castle", "image_generation", "fantasy", "fantasy"),
    ("ultra realistic premium quality face portrait", "image_generation", "realistic", "flux_premium"),
    ("anime general art of a fox girl", "image_generation", "anime", "anime_general"),
    ("write me a python function to sort a list", "coding", None, None),
    ("what's the weather like today", "chat", None, None),
    ("dark psychological seinen anime anti-hero in ruins", "image_generation", "anime", "anime_seinen"),
    ("soft pastel magical girl with flowers", "image_generation", "anime", "anime_shojo"),
]

# ANSI colours for terminal output
_GREEN = "\033[92m"
_RED = "\033[91m"
_YELLOW = "\033[93m"
_CYAN = "\033[96m"
_RESET = "\033[0m"
_BOLD = "\033[1m"


def _col(text: str, colour: str) -> str:
    return f"{colour}{text}{_RESET}"


def _check(passed: bool) -> str:
    return _col("PASS", _GREEN) if passed else _col("FAIL", _RED)


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = [
    "intent", "style_family", "anime_genre", "visual_mode",
    "needs_reference_analysis", "needs_upscale", "needs_face_detail",
    "selected_checkpoint", "selected_workflow",
    "anime_score", "realism_score", "fantasy_score", "confidence",
]

VALID_INTENTS = {"chat", "coding", "image_generation", "image_edit", "image_analysis", "planning"}
VALID_STYLES = {None, "anime", "realistic", "fantasy"}
VALID_MODES = {"portrait", "landscape", "action", "cinematic", "casual", "square"}


def validate_route_result(result: dict) -> list:
    """Return a list of validation error strings (empty means valid)."""
    errors = []
    for field in REQUIRED_FIELDS:
        if field not in result:
            errors.append(f"Missing field: {field}")

    if result.get("intent") not in VALID_INTENTS:
        errors.append(f"Invalid intent: {result.get('intent')}")

    if result.get("style_family") not in VALID_STYLES:
        errors.append(f"Invalid style_family: {result.get('style_family')}")

    if result.get("visual_mode") not in VALID_MODES:
        errors.append(f"Invalid visual_mode: {result.get('visual_mode')}")

    for score_key in ("anime_score", "realism_score", "fantasy_score", "confidence"):
        val = result.get(score_key)
        if not isinstance(val, (int, float)) or not (0.0 <= val <= 1.0):
            errors.append(f"Invalid score {score_key}={val}")

    return errors


# ---------------------------------------------------------------------------
# Main test runner
# ---------------------------------------------------------------------------

async def run_tests():
    router = RouterBrain()

    print()
    print(_col("=" * 100, _BOLD))
    print(_col("  Mini Assistant — Router Brain Test Suite", _BOLD))
    print(_col("=" * 100, _BOLD))
    print()

    # Table header
    col_widths = [48, 18, 12, 22, 10, 10]
    headers = ["Prompt", "Intent", "Style", "Checkpoint", "Conf", "Status"]
    header_row = "  ".join(h.ljust(w) for h, w in zip(headers, col_widths))
    print(_col(header_row, _CYAN))
    print("-" * 126)

    pass_count = 0
    fail_count = 0
    validation_failures = []
    all_results = []

    for prompt, expected_intent, expected_style, expected_checkpoint in TEST_PROMPTS:
        t0 = time.perf_counter()
        try:
            result = await router.route(prompt)
        except Exception as exc:
            result = {"intent": "chat", "style_family": None, "confidence": 0.0,
                      "selected_checkpoint": None, "_error": str(exc)}
        elapsed_ms = (time.perf_counter() - t0) * 1000

        all_results.append((prompt, result, elapsed_ms))

        intent = result.get("intent", "?")
        style = result.get("style_family") or "-"
        checkpoint = result.get("selected_checkpoint") or "-"
        confidence = result.get("confidence", 0.0)

        # Intent + style pass/fail
        intent_ok = (intent == expected_intent)
        style_ok = (expected_style is None or style == expected_style)
        checkpoint_ok = (expected_checkpoint is None or checkpoint == expected_checkpoint)
        overall_ok = intent_ok and style_ok and checkpoint_ok

        # JSON validation
        errors = validate_route_result(result)
        if errors:
            validation_failures.append((prompt, errors))
            overall_ok = False

        status = _check(overall_ok)
        if overall_ok:
            pass_count += 1
        else:
            fail_count += 1

        row = "  ".join([
            prompt[:col_widths[0]].ljust(col_widths[0]),
            _col(intent.ljust(col_widths[1]), _GREEN if intent_ok else _RED),
            _col(style.ljust(col_widths[2]), _GREEN if style_ok else _RED),
            _col(checkpoint.ljust(col_widths[3]), _GREEN if checkpoint_ok else _YELLOW),
            f"{confidence:.2f}".ljust(col_widths[4]),
            status,
        ])
        print(row)

    print("-" * 126)
    print(f"\nResults: {_col(str(pass_count), _GREEN)} passed, {_col(str(fail_count), _RED)} failed\n")

    # ------------------------------------------------------------------
    # Detailed validation failures
    # ------------------------------------------------------------------
    if validation_failures:
        print(_col("JSON Validation Failures:", _RED))
        for prompt, errors in validation_failures:
            print(f"  Prompt: '{prompt[:60]}'")
            for e in errors:
                print(f"    - {e}")
        print()

    # ------------------------------------------------------------------
    # Score distribution analysis
    # ------------------------------------------------------------------
    print(_col("Score Analysis:", _CYAN))
    for prompt, result, elapsed in all_results:
        a = result.get("anime_score", 0)
        r = result.get("realism_score", 0)
        f = result.get("fantasy_score", 0)
        conf = result.get("confidence", 0)
        print(
            f"  [{elapsed:5.0f}ms] {prompt[:50]:<50} "
            f"anime={a:.2f} real={r:.2f} fantasy={f:.2f} conf={conf:.2f}"
        )

    # ------------------------------------------------------------------
    # Fallback brain test
    # ------------------------------------------------------------------
    print()
    print(_col("Fallback Brain Test (keyword-only routing):", _CYAN))
    keyword_result = router._apply_keyword_rules("draw a shonen warrior with energy aura")
    print(f"  Input: 'draw a shonen warrior with energy aura'")
    print(f"  Result: {json.dumps(keyword_result, indent=4)}")
    fb_ok = keyword_result.get("intent") == "image_generation" and keyword_result.get("selected_checkpoint") == "anime_shonen"
    print(f"  Status: {_check(fb_ok)}")

    # ------------------------------------------------------------------
    # Confidence scoring test
    # ------------------------------------------------------------------
    print()
    print(_col("Keyword Scoring Test:", _CYAN))
    score_cases = [
        ("anime fox girl with sword", "anime"),
        ("DSLR portrait photography natural light", "realistic"),
        ("dragon castle fantasy RPG wizard", "fantasy"),
    ]
    for text, expected_dominant in score_cases:
        scores = router._score_request_text(text.lower())
        dominant = max(scores, key=lambda k: scores[k]).replace("_score", "")
        ok = dominant == expected_dominant
        print(
            f"  '{text[:45]:<45}' → dominant={dominant:<10} {_check(ok)} "
            f"(a={scores['anime_score']:.2f} r={scores['realism_score']:.2f} f={scores['fantasy_score']:.2f})"
        )

    print()
    overall_pass = fail_count == 0 and not validation_failures
    print(_col("=" * 100, _BOLD))
    print(_col(f"  OVERALL: {'ALL TESTS PASSED' if overall_pass else 'SOME TESTS FAILED'}", _GREEN if overall_pass else _RED))
    print(_col("=" * 100, _BOLD))
    print()

    return overall_pass


if __name__ == "__main__":
    success = asyncio.run(run_tests())
    sys.exit(0 if success else 1)
