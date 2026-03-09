"""
Startup availability checker for the image system.

Verifies:
  - Every required Ollama model is available
  - Every ComfyUI checkpoint file exists (via API and/or local filesystem)
  - Every workflow JSON file exists on disk

Returns a structured readiness report. Never raises — always fails gracefully.
"""
import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).parent.parent / "config"
WORKFLOW_DIR = CONFIG_DIR / "workflows"


# ── Individual checks ─────────────────────────────────────────────────────────

async def check_ollama_models(
    base_url: str, required_models: List[str]
) -> Dict[str, Any]:
    """Check which of the required Ollama models are available."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{base_url}/api/tags")
            r.raise_for_status()
            models_data = r.json().get("models", [])
            available_full = {m["name"] for m in models_data}
            available_base = {m["name"].split(":")[0] for m in models_data}
    except Exception as exc:
        logger.warning("Could not reach Ollama at %s: %s", base_url, exc)
        return {m: {"available": False, "error": str(exc)} for m in required_models}

    results: Dict[str, Any] = {}
    for model in required_models:
        base = model.split(":")[0]
        ok = model in available_full or base in available_base
        results[model] = {
            "available": ok,
            "error": None if ok else f"'{model}' not found in Ollama (run: ollama pull {model})",
        }
    return results


async def check_comfyui_checkpoints(
    base_url: str,
    required_checkpoints: List[str],
    local_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Check which checkpoints are available via ComfyUI API or local filesystem."""
    api_available: set = set()
    local_available: set = set()

    # Try ComfyUI object_info endpoint
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{base_url}/object_info/CheckpointLoaderSimple")
            data = r.json()
            ckpt_list = (
                data.get("CheckpointLoaderSimple", {})
                .get("input", {})
                .get("required", {})
                .get("ckpt_name", [[]])[0]
            )
            if isinstance(ckpt_list, list):
                api_available = set(ckpt_list)
    except Exception as exc:
        logger.debug("ComfyUI checkpoint API check failed: %s", exc)

    # Also scan local filesystem if path provided
    if local_path:
        p = Path(local_path)
        if p.exists():
            local_available = {f.name for f in p.rglob("*.safetensors")}
            local_available |= {f.name for f in p.rglob("*.ckpt")}

    results: Dict[str, Any] = {}
    for ckpt in required_checkpoints:
        in_api = ckpt in api_available
        in_local = ckpt in local_available
        ok = in_api or in_local
        results[ckpt] = {
            "available": ok,
            "found_via": "comfyui_api" if in_api else ("local_fs" if in_local else None),
            "error": None if ok else (
                f"'{ckpt}' not found. Place it in ComfyUI/models/checkpoints/"
            ),
        }
    return results


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
    ollama_url: str,
    comfyui_url: str,
    model_registry: Dict,
    workflow_registry: Dict,
    checkpoint_local_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Run all availability checks and return a structured report."""
    ollama_models = [
        v["model"] for v in model_registry.get("ollama_models", {}).values()
    ]
    checkpoints = [
        v["file"] for v in model_registry.get("image_checkpoints", {}).values()
    ]
    workflows = [
        v.get("file", "")
        for v in workflow_registry.values()
        if isinstance(v, dict) and v.get("file")
    ]

    ollama_results, ckpt_results = await asyncio.gather(
        check_ollama_models(ollama_url, ollama_models),
        check_comfyui_checkpoints(comfyui_url, checkpoints, checkpoint_local_path),
    )
    wf_results = check_workflow_files(workflows)

    all_ok = (
        all(v["available"] for v in ollama_results.values())
        and all(v["available"] for v in ckpt_results.values())
        and all(v["available"] for v in wf_results.values())
    )

    return {
        "ready": all_ok,
        "ollama_models": ollama_results,
        "checkpoints": ckpt_results,
        "workflows": wf_results,
        "summary": {
            "ollama_ok": sum(1 for v in ollama_results.values() if v["available"]),
            "ollama_total": len(ollama_results),
            "checkpoints_ok": sum(1 for v in ckpt_results.values() if v["available"]),
            "checkpoints_total": len(ckpt_results),
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

    ollama_ok = s["ollama_ok"] == s["ollama_total"]
    print(f"\n  Ollama Models   [{icon(ollama_ok)}]  {s['ollama_ok']}/{s['ollama_total']} available")
    for name, v in report["ollama_models"].items():
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
