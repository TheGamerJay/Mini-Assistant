"""
Mini Assistant — System Test Matrix
Run directly: python -m mini_assistant.system.test_system
"""

from .control import detect_intent, extract_context, should_act, IntentResult
from .validation import validate_response, safe_return


def _check(results: list, name: str, condition: bool) -> None:
    status = "PASS" if condition else "FAIL"
    results.append((name, status))
    mark = "+" if condition else "x"
    print(f"  [{mark}] {name}")


def run_tests() -> bool:
    results: list[tuple[str, str]] = []
    print("\n── Mini Assistant System Tests ──────────────────────\n")

    # ── INTENT DETECTION ─────────────────────────────────

    print("Intent Detection")

    r = detect_intent("do the thing")
    _check(results, "vague prompt → ambiguous", r.ambiguous)

    r = detect_intent("build me a login page and fix the existing auth flow")
    _check(results, "multi-intent → multiple detected", len(r.multiple) >= 2)

    r = detect_intent("create a new dashboard component")
    _check(results, "build intent → detected with confidence", r.intent == "build" and r.confidence >= 0.4)

    r = detect_intent("edit image to change the header title color")
    _check(results, "image_edit intent → detected", r.intent == "image_edit")

    r = detect_intent("generate an image of a futuristic city")
    _check(results, "image intent → detected", r.intent == "image")

    # ── CONTEXT EXTRACTION ───────────────────────────────

    print("\nContext Extraction")

    ctx = extract_context("delete all user data from the database completely")
    _check(results, "destructive + scope → high risk", ctx.get("is_destructive") and ctx.get("risk_level") == "high")

    ctx = extract_context("remove the old log file")
    _check(results, "destructive without scope → medium risk", ctx.get("is_destructive") and ctx.get("risk_level") == "medium")

    ctx = extract_context("build a react app with fastapi backend")
    _check(results, "language/framework extracted", ctx.get("framework") is not None)

    # ── ACT vs ASK GATING ────────────────────────────────

    print("\nAct vs Ask")

    ir = IntentResult(intent="image", confidence=0.9, matched_signals=["image of"])
    act, reason = should_act(ir, {}, token_estimate=4000)
    _check(results, "high-cost image → ask", not act and "high_cost" in reason)

    ir = IntentResult(intent="build", confidence=0.85, matched_signals=["build"])
    act, reason = should_act(ir, {"missing_critical_info": True, "missing_field": "language"})
    _check(results, "missing context → ask", not act and "missing" in reason)

    ir = IntentResult(intent="edit", confidence=0.45, matched_signals=["edit"])
    act, reason = should_act(ir, {})
    _check(results, "low confidence → ask", not act and "low_confidence" in reason)

    ir = IntentResult(intent="edit", confidence=0.9, matched_signals=["delete"])
    act, reason = should_act(ir, {"is_destructive": True, "risk_level": "high"})
    _check(results, "destructive high risk → ask", not act and "destructive_high_risk" == reason)

    ir = IntentResult(intent="chat", confidence=0.85, matched_signals=["explain"])
    act, reason = should_act(ir, {})
    _check(results, "clear chat intent → act", act and reason == "ok")

    # ── VALIDATION ───────────────────────────────────────

    print("\nValidation")

    r = validate_response({"text": "Sure, here is your app. It does lots of things."}, "build")
    _check(results, "build mode without code → invalid", not r.valid)

    r = validate_response({"text": "```python\ndef hello():\n    return 'world'\n```"}, "build")
    _check(results, "build mode with fenced code → valid", r.valid)

    r = validate_response({"text": "import React from 'react'\nconst App = () => <div/>"}, "build")
    _check(results, "build mode with code signals → valid", r.valid)

    r = validate_response({"text": "I made some changes to your code."}, "image_edit")
    _check(results, "image_edit mode without real edits → invalid", not r.valid)

    r = validate_response({
        "source_image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAE=",
        "instruction": "Make the background darker and add a blue tint",
        "edit_type": "recolor",
    }, "image_edit")
    _check(results, "image_edit mode with source image + instruction → valid", r.valid)

    r = validate_response({"text": "Here is a nice image for you."}, "image")
    _check(results, "image mode text-only → invalid", not r.valid)

    r = validate_response({"image_prompt": "short"}, "image")
    _check(results, "image mode prompt too short → invalid", not r.valid)

    r = validate_response({
        "image_prompt": "A futuristic city at night, neon lights, cinematic, wide angle shot",
        "canvas": "wide",
        "negative_prompt": "no blur, no distortion, no artifacts",
    }, "image")
    _check(results, "image mode valid structure → valid", r.valid)

    r = validate_response({
        "image_prompt": "A product shot of a white bottle",
        "canvas": "bad_value",
    }, "image")
    _check(results, "image mode invalid canvas → invalid", not r.valid)

    r = validate_response({"text": ""}, "chat")
    _check(results, "chat mode empty → invalid", not r.valid)

    r = validate_response({"text": "Here is a clear answer to your question."}, "chat")
    _check(results, "chat mode with text → valid", r.valid)

    # ── HALLUCINATION ────────────────────────────────────

    print("\nHallucination Detection")

    r = validate_response({"text": "This is 100% guaranteed to work every time."}, "chat")
    _check(results, "overconfident claim → invalid", not r.valid)

    r = validate_response({"text": "As of my last update, this API was available — this may be outdated."}, "chat")
    _check(results, "valid transparency statement → not blocked", r.valid)

    # ── SAFE RETURN ──────────────────────────────────────

    print("\nSafe Return")

    out = safe_return({"text": "Clear answer here."}, "chat")
    _check(results, "safe_return valid → ok=True", out["ok"] is True)

    out = safe_return({"text": ""}, "chat")
    _check(results, "safe_return invalid → ok=False with message", out["ok"] is False and "message" in out)

    # ── SUMMARY ──────────────────────────────────────────

    passed = sum(1 for _, s in results if s == "PASS")
    failed = len(results) - passed
    print(f"\n── Results: {passed}/{len(results)} passed", f"| {failed} failed" if failed else "| all clear", "──\n")
    return failed == 0


if __name__ == "__main__":
    import sys
    ok = run_tests()
    sys.exit(0 if ok else 1)