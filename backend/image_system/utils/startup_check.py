"""
Startup availability checker for the image system.

Verifies:
  - Required API keys are set (ANTHROPIC_API_KEY, OPENAI_API_KEY)
  - Every workflow JSON file exists on disk

No Ollama or ComfyUI dependency — image generation uses OpenAI DALL-E.
Returns a structured readiness report. Never raises — always fails gracefully.
"""
import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).parent.parent / "config"
WORKFLOW_DIR = CONFIG_DIR / "workflows"


# ── Individual checks ─────────────────────────────────────────────────────────

import os as _os

def check_api_keys() -> Dict[str, Any]:
    """Check that required API keys are set."""
    results: Dict[str, Any] = {}
    for key_name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        val = _os.environ.get(key_name, "")
        ok = bool(val)
        results[key_name] = {
            "available": ok,
            "error": None if ok else f"{key_name} is not set in environment variables",
        }
    return results


async def check_comfyui_checkpoints(
    base_url: str = "",
    required_checkpoints: List[str] = None,
    local_path: Optional[str] = None,
) -> Dict[str, Any]:
    """No-op stub — ComfyUI removed. Image generation uses OpenAI DALL-E."""
    return {}


def check_workflow_files(required_workflows: List[str]) -> Dict[str, Any]:
    """Check which workflow JSON files exist on disk."""
    results: Dict[str, Any] = {}
    for wf in required_workflows:
        path = WORKFLOW_DIR / wf
        exists = path.exists()
        results[wf] = {
            "available": exists,
            "path": str(path),
            "error": None if exists else f"File not found: {path}",
        }
    return results


# ── Full check orchestration ───────────────────────────────────────────────────

async def run_full_check(
    ollama_url: str = "",
    comfyui_url: str = "",
    model_registry: Dict = None,
    workflow_registry: Dict = None,
    checkpoint_local_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Run all availability checks and return a structured report."""
    model_registry = model_registry or {}
    workflow_registry = workflow_registry or {}
    workflows = [
        v.get("file", "")
        for v in workflow_registry.values()
        if isinstance(v, dict) and v.get("file")
    ]

    api_key_results = check_api_keys()
    wf_results = check_workflow_files(workflows)

    all_ok = (
        all(v["available"] for v in api_key_results.values())
        and all(v["available"] for v in wf_results.values())
    )

    return {
        "ready": all_ok,
        "api_keys": api_key_results,
        "checkpoints": {},
        "workflows": wf_results,
        "summary": {
            "api_keys_ok": sum(1 for v in api_key_results.values() if v["available"]),
            "api_keys_total": len(api_key_results),
            "checkpoints_ok": 0,
            "checkpoints_total": 0,
            "workflows_ok": sum(1 for v in wf_results.values() if v["available"]),
            "workflows_total": len(wf_results),
        },
    }


def print_report(report: Dict[str, Any]):
    """Pretty-print the readiness report to stdout."""
    def icon(ok: bool) -> str:
        return "✓" if ok else "✗"

    s = report["summary"]
    print("\n" + "=" * 62)
    print("  IMAGE SYSTEM — READINESS REPORT")
    print("=" * 62)

    keys_ok = s["api_keys_ok"] == s["api_keys_total"]
    print(f"\n  API Keys        [{icon(keys_ok)}]  {s['api_keys_ok']}/{s['api_keys_total']} set")
    for name, v in report.get("api_keys", {}).items():
        suffix = f"  ← {v['error']}" if not v["available"] else ""
        print(f"    {icon(v['available'])} {name}{suffix}")

    ckpt_ok = s["checkpoints_ok"] == s["checkpoints_total"]
    print(f"\n  Checkpoints     [{icon(ckpt_ok)}]  {s['checkpoints_ok']}/{s['checkpoints_total']} available")
    for name, v in report["checkpoints"].items():
        suffix = f"  ← {v['error']}" if not v["available"] else ""
        print(f"    {icon(v['available'])} {name}{suffix}")

    wf_ok = s["workflows_ok"] == s["workflows_total"]
    print(f"\n  Workflow Files  [{icon(wf_ok)}]  {s['workflows_ok']}/{s['workflows_total']} available")
    for name, v in report["workflows"].items():
        suffix = f"  ← {v['error']}" if not v["available"] else ""
        print(f"    {icon(v['available'])} {name}{suffix}")

    status = "READY ✓" if report["ready"] else "NOT READY ✗  — see items marked ✗ above"
    print(f"\n  Overall Status  :  {status}")
    print("=" * 62 + "\n")
