"""
memory/tr_loader.py — Targeted Retrieval (TR) memory loader.

Loads scoped, flat JSON memory files for a given module and user.
No embeddings. No vector DB. No full history dumps.

Memory files live at:
  memory_store/tr/{user_id}/{module}/{scope_key}.json

CEO decides what scope to load (memory_decider.py).
TR loader executes that decision — it does not decide scope itself.

Rules:
- load only the keys in the requested scope
- return empty dict if file missing — caller decides how to handle
- never fabricate missing data
- most recent entries are returned first within each scope key
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("ceo_router.tr_loader")

_BASE = Path(__file__).resolve().parents[3] / "memory_store" / "tr"


def load_scope(
    user_id:    str,
    module:     str,
    scope_str:  str,
) -> dict[str, Any]:
    """
    Load TR memory for user + module, filtered to requested scope keys.

    scope_str format: "module_name:key1,key2,key3"
    Example: "task_assist:resume,skills,applications"

    Returns a dict of {key: data} — missing keys are omitted (not None).
    """
    if not user_id:
        return {}

    # Parse scope string
    keys = _parse_scope_keys(scope_str)
    if not keys:
        return {}

    result: dict[str, Any] = {}
    base_path = _BASE / user_id / module

    for key in keys:
        file_path = base_path / f"{key}.json"
        data = _read_json(file_path)
        if data is not None:
            result[key] = data

    if not result:
        log.debug("TR: no memory found for user=%s module=%s scope=%s", user_id, module, scope_str)

    return result


def memory_available(user_id: str, module: str, scope_str: str) -> bool:
    """Check if at least one key in the scope has stored data."""
    data = load_scope(user_id, module, scope_str)
    return bool(data)


def _parse_scope_keys(scope_str: str) -> list[str]:
    """Extract key names from 'module:key1,key2' format."""
    if ":" in scope_str:
        _, keys_part = scope_str.split(":", 1)
    else:
        keys_part = scope_str
    return [k.strip() for k in keys_part.split(",") if k.strip()]


def _read_json(path: Path) -> Optional[Any]:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("TR: failed to read %s — %s", path, exc)
    return None
