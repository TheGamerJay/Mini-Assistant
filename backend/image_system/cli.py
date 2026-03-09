"""
CLI test tool for the Mini Assistant image system.

Usage:
    python -m backend.image_system.cli route  "a shonen anime warrior"
    python -m backend.image_system.cli status
    python -m backend.image_system.cli generate "a cozy cafe scene" --dry-run
    python -m backend.image_system.cli generate "a fantasy dragon" --quality high
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _print_json(data: dict) -> None:
    print(json.dumps(data, indent=2, default=str))


def _print_table(rows: list[tuple], headers: list[str]) -> None:
    """Print a simple ASCII table."""
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))

    sep = "+-" + "-+-".join("-" * w for w in col_widths) + "-+"
    header_line = "| " + " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers)) + " |"
    print(sep)
    print(header_line)
    print(sep)
    for row in rows:
        line = "| " + " | ".join(str(c).ljust(col_widths[i]) for i, c in enumerate(row)) + " |"
        print(line)
    print(sep)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

async def cmd_route(prompt: str, json_output: bool) -> None:
    """Classify a prompt and display the routing decision."""
    from backend.image_system.brains.router_brain import RouterBrain
    from backend.image_system.utils.routing_guard import validate_route

    brain = RouterBrain()
    start = time.perf_counter()
    result = await brain.route(prompt)
    result = validate_route(result)
    elapsed = (time.perf_counter() - start) * 1000

    if json_output:
        _print_json(result)
        return

    print(f"\n=== Router Decision ({elapsed:.0f}ms) ===")
    print(f"  Prompt      : {prompt[:80]}")
    print(f"  Intent      : {result.get('intent')}")
    print(f"  Style       : {result.get('style_family')} / {result.get('anime_genre')}")
    print(f"  Visual mode : {result.get('visual_mode')}")
    print(f"  Checkpoint  : {result.get('selected_checkpoint')}")
    print(f"  Workflow    : {result.get('selected_workflow')}")
    print(f"  Confidence  : {result.get('confidence', 0):.2f}")
    print(f"  Anime score : {result.get('anime_score', 0):.2f}")
    print(f"  Realism     : {result.get('realism_score', 0):.2f}")
    print(f"  Fantasy     : {result.get('fantasy_score', 0):.2f}")
    if result.get("_low_confidence_warning"):
        print(f"\n  ⚠ LOW CONF  : {result['_low_confidence_warning']}")
    if result.get("_compatibility_warning"):
        print(f"  ⚠ COMPAT    : {result['_compatibility_warning']}")


async def cmd_status(json_output: bool) -> None:
    """Check which Ollama models and ComfyUI checkpoints are available."""
    from backend.image_system.utils.startup_check import run_full_check, print_report

    report = await run_full_check()

    if json_output:
        _print_json(report)
        return

    print_report(report)


async def cmd_generate(
    prompt: str,
    quality: str,
    dry_run: bool,
    json_output: bool,
    checkpoint: str | None,
    workflow: str | None,
    seed: int | None,
) -> None:
    """Run the full generation pipeline (or dry-run)."""
    import httpx

    payload = {
        "prompt": prompt,
        "quality": quality,
        "dry_run": dry_run,
    }
    if checkpoint:
        payload["override_checkpoint"] = checkpoint
    if workflow:
        payload["override_workflow"] = workflow
    if seed is not None:
        payload["override_seed"] = seed

    url = "http://localhost:7860/api/image/generate"
    print(f"\nPOST {url}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    print()

    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=360) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.ConnectError:
        print("ERROR: Could not connect to image server at localhost:7860.")
        print("Start it with: uvicorn backend.image_system.api.server:app --port 7860")
        sys.exit(1)
    except Exception as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)

    elapsed = (time.perf_counter() - start) * 1000

    if json_output:
        _print_json(data)
        return

    print(f"=== Generation Result ({elapsed:.0f}ms) ===")
    print(f"  Session     : {data.get('session_id')}")
    print(f"  Dry run     : {data.get('dry_run', False)}")

    rr = data.get("route_result", {})
    print(f"  Intent      : {rr.get('intent')}")
    print(f"  Checkpoint  : {rr.get('selected_checkpoint')}")
    print(f"  Workflow    : {rr.get('selected_workflow')}")
    print(f"  Confidence  : {rr.get('confidence', 0):.2f}")

    if data.get("plan"):
        plan = data["plan"]
        print(f"\n  --- Plan ---")
        print(f"  Checkpoint  : {plan.get('checkpoint_file')}")
        print(f"  Size        : {plan.get('width')}x{plan.get('height')}")
        print(f"  Steps       : {plan.get('steps')}")
        print(f"  CFG         : {plan.get('cfg')}")
        print(f"  Positive    : {plan.get('positive_prompt', '')[:120]}...")
        print(f"  Negative    : {plan.get('negative_prompt', '')[:80]}...")

    if data.get("image_base64"):
        img_b64 = data["image_base64"]
        import base64
        img_bytes = base64.b64decode(img_b64)
        out_path = Path(f"cli_output_{int(time.time())}.png")
        out_path.write_bytes(img_bytes)
        print(f"\n  Image saved : {out_path.resolve()}")
    else:
        print("\n  No image generated.")

    if data.get("prompt_warnings"):
        print(f"\n  Warnings    : {data['prompt_warnings']}")


async def cmd_batch_route(prompts: list[str]) -> None:
    """Route a batch of prompts and print a summary table."""
    from backend.image_system.brains.router_brain import RouterBrain
    from backend.image_system.utils.routing_guard import validate_route

    brain = RouterBrain()
    rows = []
    print(f"\nRouting {len(prompts)} prompts...\n")

    for i, p in enumerate(prompts, 1):
        start = time.perf_counter()
        try:
            result = await brain.route(p)
            result = validate_route(result)
            elapsed = (time.perf_counter() - start) * 1000
            rows.append((
                i,
                p[:40] + "..." if len(p) > 40 else p,
                result.get("intent", "-"),
                result.get("selected_checkpoint", "-"),
                f"{result.get('confidence', 0):.2f}",
                f"{elapsed:.0f}ms",
            ))
        except Exception as exc:
            rows.append((i, p[:40], "ERROR", str(exc)[:30], "-", "-"))

    _print_table(rows, ["#", "Prompt", "Intent", "Checkpoint", "Conf", "Time"])


# ---------------------------------------------------------------------------
# Default test prompts for batch mode
# ---------------------------------------------------------------------------

_DEFAULT_PROMPTS = [
    "draw a shonen anime warrior with power aura",
    "generate a realistic portrait photo in studio lighting",
    "paint a fantasy dragon over a dark castle",
    "create a cute anime girl in a school uniform",
    "make a cozy cafe slice of life scene",
    "show a dark psychological seinen story",
    "ultra realistic 8k flux premium quality portrait",
    "hello, how are you?",
    "write a python function to sort a list",
    "romantic anime couple with cherry blossoms",
]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m backend.image_system.cli",
        description="Mini Assistant Image System CLI",
    )
    parser.add_argument("--json", action="store_true", dest="json_output",
                        help="Output raw JSON instead of formatted text")

    sub = parser.add_subparsers(dest="command")

    # route
    p_route = sub.add_parser("route", help="Classify a prompt and show routing decision")
    p_route.add_argument("prompt", help="Prompt text to classify")

    # status
    sub.add_parser("status", help="Check Ollama and ComfyUI availability")

    # generate
    p_gen = sub.add_parser("generate", help="Run the full generation pipeline")
    p_gen.add_argument("prompt", help="Image generation prompt")
    p_gen.add_argument("--quality", default="balanced", choices=["fast", "balanced", "high"])
    p_gen.add_argument("--dry-run", action="store_true", help="Plan only, do not generate")
    p_gen.add_argument("--checkpoint", default=None)
    p_gen.add_argument("--workflow", default=None)
    p_gen.add_argument("--seed", type=int, default=None)

    # batch
    p_batch = sub.add_parser("batch", help="Route a batch of default test prompts")
    p_batch.add_argument("prompts", nargs="*", help="Optional custom prompts; uses defaults if omitted")

    args = parser.parse_args()

    if args.command == "route":
        asyncio.run(cmd_route(args.prompt, args.json_output))
    elif args.command == "status":
        asyncio.run(cmd_status(args.json_output))
    elif args.command == "generate":
        asyncio.run(cmd_generate(
            args.prompt, args.quality, args.dry_run, args.json_output,
            args.checkpoint, args.workflow, args.seed,
        ))
    elif args.command == "batch":
        prompts = args.prompts or _DEFAULT_PROMPTS
        asyncio.run(cmd_batch_route(prompts))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
