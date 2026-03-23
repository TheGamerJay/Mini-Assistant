"""
Build Patterns Library — shared knowledge across all users
==========================================================
When a build passes the debug agent clean (all_clear), key structural
patterns are extracted from the HTML and saved to a global shared file.

Next time ANY user asks for something similar, the Search Brain finds
these patterns and feeds them to Claude — so it already knows the right
architecture before writing a single line.

Storage: memory_store/build_patterns.json
Format:  [{id, app_type, title, patterns, tech_notes, features,
           css_vars, timestamp, use_count}]

Extraction is rule-based (no LLM calls) — fast, cheap, deterministic.
"""
from __future__ import annotations

import json
import logging
import re
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PATTERNS_FILE = Path(__file__).parent.parent.parent.parent / "memory_store" / "build_patterns.json"
_MAX_PATTERNS  = 200   # keep newest 200 patterns
_PROMPT_LIMIT  = 4     # inject top-4 into system prompts


# ---------------------------------------------------------------------------
# App type detection
# ---------------------------------------------------------------------------

_APP_TYPE_RULES: list[tuple[str, re.Pattern]] = [
    ("canvas_game",    re.compile(r'canvas\.getContext|requestAnimationFrame', re.I)),
    ("endless_runner", re.compile(r'endless.?runner|subway|lane.{0,20}switch|obstacle.{0,30}lane', re.I)),
    ("platformer",     re.compile(r'platformer|gravity|jump.{0,20}platform|ground.*collision', re.I)),
    ("puzzle_game",    re.compile(r'grid\[|puzzle|match.{0,10}3|tile.{0,20}click|sudoku', re.I)),
    ("quiz_game",      re.compile(r'quiz|question.*answer|score.*correct|nextQuestion', re.I)),
    ("todo_app",       re.compile(r'todo|task.*list|addTask|removeTask|completeTodo', re.I)),
    ("dashboard",      re.compile(r'dashboard|chart|graph|metric|stat.*card|kpi', re.I)),
    ("calculator",     re.compile(r'calculator|calc\b|display.*=|operand|operator.*stack', re.I)),
    ("timer",          re.compile(r'countdown|stopwatch|setInterval.*second|timer.*start', re.I)),
    ("chat_app",       re.compile(r'sendMessage|chatbubble|message.*list|chat.*input', re.I)),
    ("portfolio",      re.compile(r'portfolio|about.*me|my.*projects|hero.*section', re.I)),
    ("form_app",       re.compile(r'<form|form.*submit|validateForm|formData', re.I)),
    ("ecommerce",      re.compile(r'cart|addToCart|checkout|product.*price|shop.*item', re.I)),
    ("music_app",      re.compile(r'AudioContext|playNote|frequency|oscillator|beat', re.I)),
    ("drawing_app",    re.compile(r'mousedown.*draw|canvas.*mouse|pencil|eraser.*tool', re.I)),
]

def _detect_app_type(html: str) -> str:
    for name, pattern in _APP_TYPE_RULES:
        if pattern.search(html):
            return name
    return "general"


# ---------------------------------------------------------------------------
# Feature / pattern extraction
# ---------------------------------------------------------------------------

_FEATURE_RULES: list[tuple[str, re.Pattern]] = [
    ("localStorage persistence",     re.compile(r'localStorage\.(set|get)Item', re.I)),
    ("in-app shop / store",          re.compile(r'\bshop\b|\bstore\b.*buy|spend.*banana|spend.*coin|purchase.*item', re.I)),
    ("unlockable skins",             re.compile(r'skin.*unlock|unlock.*skin|color.*skin|equip.*skin', re.I)),
    ("currency system",              re.compile(r'banana|coin|gem|gold|credit.*count|currency', re.I)),
    ("particle effects",             re.compile(r'particle|sparkle|explode|confetti', re.I)),
    ("parallax scrolling",           re.compile(r'parallax|bgOffset|backgroundX|scrollSpeed', re.I)),
    ("3-lane collision",             re.compile(r'LANES?\s*=\s*\[|lane\s*===?\s*\d|laneIndex', re.I)),
    ("power-ups / upgrades",         re.compile(r'magnet|shield|powerup|power.?up|upgrade.*active', re.I)),
    ("high score tracking",          re.compile(r'highScore|best.*score|localStorage.*score', re.I)),
    ("death / game-over screen",     re.compile(r'gameOver|game.over|deathScreen|showGameOver', re.I)),
    ("main menu screen",             re.compile(r'mainMenu|showMenu|menuScreen|startScreen', re.I)),
    ("smooth 60fps loop",            re.compile(r'requestAnimationFrame', re.I)),
    ("keyboard controls",            re.compile(r'keydown|ArrowLeft|ArrowRight|Space|keyCode', re.I)),
    ("touch / swipe controls",       re.compile(r'touchstart|touchend|swipe|touchmove', re.I)),
    ("CSS custom properties",        re.compile(r':root\s*\{[^}]*--', re.I)),
    ("dark neon theme",              re.compile(r'#0[0-9a-f][0-9a-f]|neon|glow|box-shadow.*rgba', re.I)),
    ("sprite / frame animation",     re.compile(r'frameX|spriteSheet|drawImage.*frame|animate.*sprite', re.I)),
    ("collision detection",          re.compile(r'collision|intersect|overlap|hitbox', re.I)),
    ("difficulty scaling",           re.compile(r'speed\s*\+=|speed\s*\*=|difficulty.*increase|level.*up', re.I)),
    ("sound effects",                re.compile(r'AudioContext|new Audio|\.play\(\)|soundEffect', re.I)),
]

def _extract_features(html: str) -> list[str]:
    return [name for name, pat in _FEATURE_RULES if pat.search(html)]


def _extract_css_vars(html: str) -> list[str]:
    """Extract CSS custom property names from :root {}."""
    m = re.search(r':root\s*\{([^}]+)\}', html, re.I)
    if not m:
        return []
    return re.findall(r'--[\w-]+', m.group(1))[:10]


def _extract_title(html: str) -> str:
    m = re.search(r'<title>([^<]+)</title>', html, re.I)
    if m:
        return m.group(1).strip()[:60]
    m = re.search(r'<h1[^>]*>([^<]+)</h1>', html, re.I)
    if m:
        return re.sub(r'\s+', ' ', m.group(1)).strip()[:60]
    return "Untitled App"


def _build_tech_notes(html: str, app_type: str, features: list[str]) -> list[str]:
    notes = []
    if app_type == "canvas_game":
        notes.append("Canvas 2D context — draw everything in requestAnimationFrame loop")
    if "3-lane collision" in features:
        notes.append("Three fixed lane X positions, collision checked by lane index not pixel rect")
    if "in-app shop / store" in features:
        notes.append("Shop modal overlays canvas, currency deducted from localStorage on purchase")
    if "unlockable skins" in features:
        notes.append("Skins stored as array with {name, color, cost, unlocked} — save to localStorage")
    if "power-ups / upgrades" in features:
        notes.append("Upgrades activated per-run, duration tracked with countdown timer on HUD")
    if "difficulty scaling" in features:
        notes.append("Speed starts slow, increases every N seconds or every score threshold")
    if "CSS custom properties" in features:
        notes.append("All colors defined as CSS vars in :root — easy to theme without hunting hex values")
    return notes


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_and_save(html: str, session_id: str | None = None) -> bool:
    """
    Extract structural patterns from a clean HTML build and save to global store.
    Returns True if saved, False if skipped (too short, duplicate type recently, etc.).
    """
    if len(html) < 2000:
        return False  # too short to be meaningful

    app_type = _detect_app_type(html)
    features = _extract_features(html)
    css_vars  = _extract_css_vars(html)
    title     = _extract_title(html)
    tech_notes = _build_tech_notes(html, app_type, features)

    if not features:
        return False  # nothing interesting to learn

    pattern = {
        "id":         str(uuid.uuid4())[:8],
        "app_type":   app_type,
        "title":      title,
        "features":   features,
        "tech_notes": tech_notes,
        "css_vars":   css_vars,
        "session_id": session_id or "unknown",
        "timestamp":  time.time(),
        "use_count":  0,
    }

    try:
        _PATTERNS_FILE.parent.mkdir(parents=True, exist_ok=True)
        existing: list[dict] = []
        if _PATTERNS_FILE.exists():
            try:
                existing = json.loads(_PATTERNS_FILE.read_text(encoding="utf-8"))
            except Exception:
                existing = []

        # Deduplicate: skip if same app_type + same feature set saved in last 5 entries
        recent = existing[-5:] if existing else []
        for r in recent:
            if r.get("app_type") == app_type and set(r.get("features", [])) == set(features):
                logger.debug("[BuildPatterns] duplicate pattern skipped: %s", app_type)
                return False

        existing.append(pattern)
        # Keep only the newest _MAX_PATTERNS
        if len(existing) > _MAX_PATTERNS:
            existing = existing[-_MAX_PATTERNS:]

        _PATTERNS_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        logger.info("[BuildPatterns] saved pattern: %s — %s (%d features)",
                    title, app_type, len(features))
        return True

    except Exception as e:
        logger.warning("[BuildPatterns] save failed (non-fatal): %s", e)
        return False


def search_patterns(query: str, top_n: int = _PROMPT_LIMIT) -> list[dict]:
    """Return patterns most relevant to query (keyword match on features + app_type)."""
    try:
        if not _PATTERNS_FILE.exists():
            return []
        data: list[dict] = json.loads(_PATTERNS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []

    q = query.lower()
    scored = []
    for p in data:
        score = 0
        if p.get("app_type", "") in q:
            score += 3
        for feat in p.get("features", []):
            # Check if any word from the feature name appears in query
            feat_words = re.findall(r"[a-z]+", feat.lower())
            score += sum(1 for w in feat_words if len(w) > 3 and w in q)
        score += p.get("use_count", 0) * 0.1  # slightly boost frequently useful patterns
        if score > 0:
            scored.append((score, p))

    scored.sort(key=lambda x: -x[0])
    results = [p for _, p in scored[:top_n]]

    # Increment use_count for returned patterns
    try:
        data_updated = False
        id_set = {p["id"] for p in results if "id" in p}
        all_data: list[dict] = json.loads(_PATTERNS_FILE.read_text(encoding="utf-8"))
        for entry in all_data:
            if entry.get("id") in id_set:
                entry["use_count"] = entry.get("use_count", 0) + 1
                data_updated = True
        if data_updated:
            _PATTERNS_FILE.write_text(json.dumps(all_data, indent=2), encoding="utf-8")
    except Exception:
        pass

    return results


def format_for_prompt(patterns: list[dict]) -> str:
    """Format matched patterns into a system prompt block."""
    if not patterns:
        return ""
    lines = ["### Proven build patterns (learned from past successful builds)"]
    for p in patterns:
        lines.append(f"\n**{p['title']}** ({p['app_type'].replace('_', ' ')})")
        for feat in p.get("features", [])[:6]:
            lines.append(f"  ✓ {feat}")
        for note in p.get("tech_notes", [])[:3]:
            lines.append(f"  → {note}")
    return "\n".join(lines)
