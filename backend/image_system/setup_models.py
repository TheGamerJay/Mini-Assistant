"""
Setup script — pulls all required Ollama models for the Mini Assistant image system.

Run from the image_system directory:
    python setup_models.py

Or from the project root:
    python -m backend.image_system.setup_models
"""

import asyncio
import json
import sys
from pathlib import Path

# Ensure the package root is importable when run directly
_PACKAGE_ROOT = Path(__file__).parent.parent.parent
if str(_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_ROOT))

_CONFIG_PATH = Path(__file__).parent / "config" / "model_registry.json"

_GREEN = "\033[92m"
_RED = "\033[91m"
_YELLOW = "\033[93m"
_CYAN = "\033[96m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def _col(text: str, colour: str) -> str:
    return f"{colour}{text}{_RESET}"


def _load_required_models() -> list:
    """Load the list of required Ollama model names from model_registry.json."""
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        registry = json.load(f)
    return [info["model"] for info in registry["ollama_models"].values()]


async def main() -> None:
    from backend.image_system.services.ollama_client import OllamaClient

    print()
    print(_col("=" * 60, _BOLD))
    print(_col("  Mini Assistant — Ollama Model Setup", _BOLD))
    print(_col("=" * 60, _BOLD))
    print()

    try:
        required_models = _load_required_models()
    except FileNotFoundError:
        print(_col(f"ERROR: Could not find {_CONFIG_PATH}", _RED))
        sys.exit(1)

    print(f"Required models ({len(required_models)}):")
    for m in required_models:
        print(f"  - {m}")
    print()

    client = OllamaClient()

    # Check Ollama is reachable
    try:
        available = await client.list_models()
        print(_col(f"Ollama is running. {len(available)} model(s) currently available.", _GREEN))
    except Exception as exc:
        print(_col(f"ERROR: Cannot reach Ollama at http://localhost:11434", _RED))
        print(_col(f"  Make sure Ollama is running: ollama serve", _YELLOW))
        print(f"  Detail: {exc}")
        sys.exit(1)

    print()

    # Check and pull each model
    pulled = []
    already_had = []
    failed = []

    for model in required_models:
        available_now = await client.check_model_available(model)
        if available_now:
            print(_col(f"  ✓  {model} already available.", _GREEN))
            already_had.append(model)
            continue

        print(_col(f"  ↓  Pulling {model} ...", _YELLOW))
        try:
            async for status_line in client.pull_model(model):
                try:
                    status = json.loads(status_line)
                    msg = status.get("status", "")
                    total = status.get("total", 0)
                    completed = status.get("completed", 0)
                    if total and completed:
                        pct = completed / total * 100
                        print(f"     {msg}: {pct:.1f}%", end="\r", flush=True)
                    elif msg:
                        print(f"     {msg}", end="\r", flush=True)
                except json.JSONDecodeError:
                    pass
            print()  # newline after progress
            print(_col(f"  ✓  {model} pulled successfully.", _GREEN))
            pulled.append(model)
        except Exception as exc:
            print()
            print(_col(f"  ✗  Failed to pull {model}: {exc}", _RED))
            failed.append(model)

    await client.close()

    # Summary
    print()
    print(_col("=" * 60, _BOLD))
    print(_col("  Setup Summary", _BOLD))
    print(_col("=" * 60, _BOLD))
    print(f"  Already available : {len(already_had)}")
    print(f"  Newly pulled      : {len(pulled)}")
    print(f"  Failed            : {len(failed)}")

    if failed:
        print()
        print(_col("  Failed models:", _RED))
        for m in failed:
            print(f"    - {m}")
        print()
        print(_col("  You can retry individual models with:", _YELLOW))
        for m in failed:
            print(f"    ollama pull {m}")
        sys.exit(1)
    else:
        print()
        print(_col("  All models are ready!", _GREEN))
        print(_col("=" * 60, _BOLD))
        print()


if __name__ == "__main__":
    asyncio.run(main())
