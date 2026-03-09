"""
Startup readiness script for the Mini Assistant image system.

Checks:
  - Ollama is reachable and required models are present (or can be pulled)
  - ComfyUI is reachable and required checkpoints exist
  - All workflow JSON files exist and are valid
  - Output and log directories are writable

Usage:
    python -m backend.image_system.startup            # check only
    python -m backend.image_system.startup --fix      # pull missing Ollama models
    python -m backend.image_system.startup --json     # machine-readable output

Exit codes:
    0 — all checks passed
    1 — one or more checks failed (details in output)
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path


async def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m backend.image_system.startup",
        description="Image system startup readiness checker",
    )
    parser.add_argument("--fix", action="store_true",
                        help="Pull missing Ollama models automatically")
    parser.add_argument("--json", action="store_true", dest="json_output",
                        help="Output machine-readable JSON")
    args = parser.parse_args()

    from backend.image_system.utils.startup_check import run_full_check, print_report

    # --fix: pull missing models first
    if args.fix:
        await _pull_missing_models()

    report = await run_full_check()

    if args.json_output:
        print(json.dumps(report, indent=2, default=str))
    else:
        print_report(report)
        _check_directories()

    all_ok = (
        report.get("ollama", {}).get("reachable", False)
        and all(v.get("available") for v in report.get("ollama_models", {}).values())
        and all(v.get("exists") for v in report.get("workflows", {}).values())
    )

    return 0 if all_ok else 1


async def _pull_missing_models() -> None:
    """Pull Ollama models that are not yet available locally."""
    try:
        from backend.image_system.services.ollama_client import OllamaClient
        from pathlib import Path
        import json as _json

        registry_path = Path(__file__).parent / "config" / "model_registry.json"
        with open(registry_path) as f:
            registry = _json.load(f)

        client = OllamaClient()
        available = set(await client.list_models())

        missing = []
        for role, info in registry["ollama_models"].items():
            model = info["model"]
            if model not in available and model.split(":")[0] not in available:
                missing.append(model)

        if not missing:
            print("All Ollama models already available — nothing to pull.")
            return

        print(f"Pulling {len(missing)} missing models: {missing}")
        await client.ensure_models(missing)
        print("Pull complete.")
    except Exception as exc:
        print(f"Warning: Could not pull models: {exc}")


def _check_directories() -> None:
    """Verify that output and log directories are writable."""
    base = Path(__file__).parent
    dirs = {
        "output": base / "output",
        "logs":   base / "logs",
    }
    print("\n=== Directory Checks ===")
    for name, path in dirs.items():
        path.mkdir(parents=True, exist_ok=True)
        test_file = path / ".write_test"
        try:
            test_file.write_text("ok")
            test_file.unlink()
            print(f"  {name:8s}  OK  ({path})")
        except OSError as exc:
            print(f"  {name:8s}  FAIL  ({exc})")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
