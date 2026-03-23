"""
User Preference Memory — Mini Assistant learns who the user is
==============================================================
Tracks user patterns across ALL sessions — not bug patterns (that's lesson_memory.py),
but USER patterns: what they build, how they like things to look, their habits.

Every session, Mini Assistant picks up signals from the conversation:
  - Do they always build games? dashboards? tools?
  - Do they prefer dark themes? neon colors? minimal/clean?
  - Do they like detailed explanations or just the code?
  - What framework/style do they gravitate to?

These preferences get injected into build/patch system prompts so every
build feels personalized without the user ever having to explain themselves.

Storage: memory_store/user_prefs.json
Format:  { "themes": [...], "app_types": [...], "style": [...], "last_seen": ... }
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_PREFS_FILE = Path(__file__).parent.parent.parent.parent / "memory_store" / "user_prefs.json"

# ── Default preference structure ──────────────────────────────────────────────

_DEFAULT_PREFS: dict = {
    "app_types":        [],   # ["game", "dashboard", "tool", "form", "portfolio", ...]
    "themes":           [],   # ["dark", "neon", "minimal", "colorful", "glassmorphism", ...]
    "color_palette":    [],   # ["purple", "cyan", "orange", "blue", ...] — dominant hues
    "style_signals":    [],   # ["animations", "gradients", "flat", "3d", "retro", ...]
    "verbosity":        None, # "brief" | "detailed" | None (unknown)
    "build_count":      0,
    "fix_count":        0,
    "last_seen":        None,
    "first_seen":       None,
}


# ── Load / Save ───────────────────────────────────────────────────────────────

def load_prefs() -> dict:
    """Load user preferences from disk. Returns defaults if file not found."""
    try:
        raw = json.loads(_PREFS_FILE.read_text(encoding="utf-8"))
        # Merge with defaults so new keys are always present
        merged = dict(_DEFAULT_PREFS)
        merged.update(raw)
        return merged
    except Exception:
        return dict(_DEFAULT_PREFS)


def _save_prefs(prefs: dict) -> None:
    try:
        _PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
        prefs["last_seen"] = datetime.now(timezone.utc).isoformat()
        if not prefs.get("first_seen"):
            prefs["first_seen"] = prefs["last_seen"]
        _PREFS_FILE.write_text(json.dumps(prefs, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        logger.warning("[UserMemory] save failed (non-fatal): %s", exc)


# ── Preference extraction ─────────────────────────────────────────────────────

_APP_TYPE_PATTERNS = {
    "game":       re.compile(r"\b(game|arcade|snake|tetris|pong|platformer|puzzle|rpg|fps|shooter|racing|breakout|pacman|mario|flappy|chess|checkers|tic.tac|minesweeper)\b", re.I),
    "dashboard":  re.compile(r"\b(dashboard|analytics|chart|graph|stats|metrics|monitor|kpi|report|visualization)\b", re.I),
    "tool":       re.compile(r"\b(tool|calculator|converter|generator|tracker|planner|scheduler|timer|stopwatch|clock|calendar)\b", re.I),
    "form":       re.compile(r"\b(form|survey|quiz|registration|login|signup|checkout|contact)\b", re.I),
    "portfolio":  re.compile(r"\b(portfolio|profile|resume|cv|about me|landing page|personal site)\b", re.I),
    "ecommerce":  re.compile(r"\b(shop|store|cart|product|ecommerce|marketplace|listing)\b", re.I),
    "social":     re.compile(r"\b(social|feed|posts|comments|profile|followers|timeline|chat|messaging)\b", re.I),
    "media":      re.compile(r"\b(music|player|playlist|video|podcast|gallery|album|photo)\b", re.I),
}

_THEME_PATTERNS = {
    "dark":          re.compile(r"\b(dark|night|black|noir)\b", re.I),
    "neon":          re.compile(r"\b(neon|cyberpunk|vaporwave|synthwave|glow|glowing|electric)\b", re.I),
    "minimal":       re.compile(r"\b(minimal|clean|simple|flat|plain|stripped)\b", re.I),
    "colorful":      re.compile(r"\b(colorful|vibrant|bright|playful|rainbow|fun)\b", re.I),
    "glassmorphism": re.compile(r"\b(glass|glassmorphism|frosted|blur|transparent|translucent)\b", re.I),
    "retro":         re.compile(r"\b(retro|vintage|pixel|8.?bit|16.?bit|arcade|old.?school)\b", re.I),
    "light":         re.compile(r"\b(light|white|clean|bright|pastel)\b", re.I),
    "gradient":      re.compile(r"\b(gradient|rainbow|multi.?color|fade|ombre)\b", re.I),
}

_COLOR_PATTERNS = {
    "purple": re.compile(r"\b(purple|violet|indigo|lavender)\b", re.I),
    "cyan":   re.compile(r"\b(cyan|teal|turquoise|aqua)\b", re.I),
    "blue":   re.compile(r"\b(blue|navy|cobalt|sapphire)\b", re.I),
    "green":  re.compile(r"\b(green|emerald|mint|lime|forest)\b", re.I),
    "orange": re.compile(r"\b(orange|amber|rust|coral)\b", re.I),
    "red":    re.compile(r"\b(red|crimson|ruby|rose|scarlet)\b", re.I),
    "pink":   re.compile(r"\b(pink|magenta|fuchsia|hot.?pink)\b", re.I),
    "gold":   re.compile(r"\b(gold|golden|yellow|bronze|metallic)\b", re.I),
}

_STYLE_PATTERNS = {
    "animations": re.compile(r"\b(animated|animations|smooth|transitions|motion|bouncy|particles)\b", re.I),
    "3d":         re.compile(r"\b(3d|three.?d|perspective|depth|isometric|voxel)\b", re.I),
    "shadows":    re.compile(r"\b(shadow|elevation|depth|card|floating)\b", re.I),
    "bold":       re.compile(r"\b(bold|big|large|huge|massive|dramatic)\b", re.I),
    "compact":    re.compile(r"\b(compact|dense|small|tight|slim)\b", re.I),
}


def extract_prefs_from_conversation(message: str, reply: str, intent: str = "") -> dict:
    """
    Scan a user message + assistant reply for preference signals.
    Returns a dict of detected signals to merge into stored prefs.
    """
    combined = message + " " + reply
    detected: dict = {
        "app_types":     [],
        "themes":        [],
        "color_palette": [],
        "style_signals": [],
    }

    for label, pattern in _APP_TYPE_PATTERNS.items():
        if pattern.search(combined):
            detected["app_types"].append(label)

    for label, pattern in _THEME_PATTERNS.items():
        if pattern.search(combined):
            detected["themes"].append(label)

    for label, pattern in _COLOR_PATTERNS.items():
        if pattern.search(combined):
            detected["color_palette"].append(label)

    for label, pattern in _STYLE_PATTERNS.items():
        if pattern.search(combined):
            detected["style_signals"].append(label)

    return detected


def update_prefs_from_conversation(
    message: str,
    reply: str,
    intent: str = "",
    was_build: bool = False,
    was_fix: bool = False,
) -> None:
    """
    Extract signals from a completed conversation turn and persist them.
    Call this after every assistant response (non-fatal, non-blocking).
    """
    try:
        prefs = load_prefs()
        signals = extract_prefs_from_conversation(message, reply, intent)

        # Merge lists (deduplicate, keep top 10 most recent)
        for key in ("app_types", "themes", "color_palette", "style_signals"):
            existing = prefs.get(key, [])
            for item in signals[key]:
                if item not in existing:
                    existing.insert(0, item)
            prefs[key] = existing[:10]

        if was_build:
            prefs["build_count"] = prefs.get("build_count", 0) + 1
        if was_fix:
            prefs["fix_count"] = prefs.get("fix_count", 0) + 1

        _save_prefs(prefs)
        logger.debug("[UserMemory] updated — types=%s themes=%s", prefs["app_types"][:3], prefs["themes"][:3])
    except Exception as exc:
        logger.warning("[UserMemory] update failed (non-fatal): %s", exc)


# ── Format for prompt injection ───────────────────────────────────────────────

def format_prefs_for_prompt() -> str:
    """
    Return a concise context block to prepend to system prompts.
    Empty string if no preferences have been learned yet.
    """
    try:
        prefs = load_prefs()

        # Need at least some signal to be useful
        has_data = any([
            prefs.get("app_types"),
            prefs.get("themes"),
            prefs.get("color_palette"),
            prefs.get("build_count", 0) > 0,
        ])
        if not has_data:
            return ""

        lines = ["\n## KNOWN USER PREFERENCES (learned from past sessions)"]
        lines.append("Apply these automatically — the user shouldn't have to ask twice.\n")

        if prefs.get("app_types"):
            top = prefs["app_types"][:4]
            lines.append(f"Favorite app types: {', '.join(top)}")
            lines.append(f"→ They know what they want from these. Build confidently, skip basic explanations.")

        if prefs.get("themes"):
            top = prefs["themes"][:3]
            lines.append(f"Preferred visual style: {', '.join(top)}")
            lines.append(f"→ Default to this style unless they specify something different.")

        if prefs.get("color_palette"):
            top = prefs["color_palette"][:4]
            lines.append(f"Color preferences: {', '.join(top)}")
            lines.append(f"→ Lean toward these colors when not specified.")

        if prefs.get("style_signals"):
            top = prefs["style_signals"][:3]
            lines.append(f"Style signals: {', '.join(top)}")

        builds = prefs.get("build_count", 0)
        fixes  = prefs.get("fix_count", 0)
        if builds > 0:
            lines.append(f"\nSession history: {builds} builds, {fixes} fixes completed.")
            if builds >= 5:
                lines.append("→ Experienced user. Skip basic onboarding language.")

        return "\n".join(lines) + "\n"

    except Exception as exc:
        logger.debug("[UserMemory] format failed (non-fatal): %s", exc)
        return ""
