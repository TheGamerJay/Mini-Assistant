"""
modules/image_edit.py — Image edit module stub.

Handles modification of attached images.
Routes to existing image_edit pipeline in image_system.
"""
from __future__ import annotations
from typing import Any

async def execute(decision: dict, memory: dict, web_results: dict) -> dict[str, Any]:
    return {"module": "image_edit", "status": "routed_to_image_edit_pipeline"}
