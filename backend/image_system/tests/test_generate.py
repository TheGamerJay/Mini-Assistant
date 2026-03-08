"""
End-to-end generation test script.

Checks Ollama, checks ComfyUI, then runs a full generation request.
Saves the output image to tests/output/.

Usage:
    python tests/test_generate.py                   # Full test
    python tests/test_generate.py --dry-run         # Skip ComfyUI call
    python tests/test_generate.py --prompt "..."    # Custom prompt
"""

import argparse
import asyncio
import base64
import json
import sys
import time
from pathlib import Path

# Make package importable when run directly
_ROOT = Path(__file__).parent.parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ANSI helpers
_GREEN = "\033[92m"
_RED = "\033[91m"
_YELLOW = "\033[93m"
_CYAN = "\033[96m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def _col(text: str, colour: str) -> str:
    return f"{colour}{text}{_RESET}"


def _section(title: str) -> None:
    print()
    print(_col(f"{'─' * 70}", _CYAN))
    print(_col(f"  {title}", _BOLD))
    print(_col(f"{'─' * 70}", _CYAN))


def _ok(msg: str) -> None:
    print(f"  {_col('✓', _GREEN)}  {msg}")


def _fail(msg: str) -> None:
    print(f"  {_col('✗', _RED)}  {msg}")


def _info(msg: str) -> None:
    print(f"  {_col('·', _YELLOW)}  {msg}")


# ---------------------------------------------------------------------------
# Check helpers
# ---------------------------------------------------------------------------

async def check_ollama() -> bool:
    """Return True if Ollama is reachable and has at least one model."""
    from backend.image_system.services.ollama_client import OllamaClient
    client = OllamaClient()
    try:
        models = await client.list_models()
        if models:
            _ok(f"Ollama is running. Found {len(models)} model(s): {', '.join(models[:5])}")
            return True
        else:
            _fail("Ollama is running but has no models pulled.")
            return False
    except Exception as exc:
        _fail(f"Cannot reach Ollama: {exc}")
        return False
    finally:
        await client.close()


async def check_required_models() -> dict:
    """Check each required model's availability. Returns {role: bool}."""
    from backend.image_system.services.ollama_client import OllamaClient, _load_registry
    client = OllamaClient()
    registry = _load_registry()
    results = {}
    try:
        for role, info in registry["ollama_models"].items():
            model = info["model"]
            available = await client.check_model_available(model)
            results[role] = available
            ((_ok if available else _fail))(
                f"  {role:20s} → {model} {'(available)' if available else '(NOT FOUND)'}"
            )
    finally:
        await client.close()
    return results


async def check_comfyui() -> bool:
    """Return True if ComfyUI is reachable."""
    from backend.image_system.services.comfyui_client import ComfyUIClient
    client = ComfyUIClient()
    try:
        status = await client.get_queue_status()
        _ok(f"ComfyUI is running. Queue: {status}")
        return True
    except Exception as exc:
        _fail(f"Cannot reach ComfyUI at http://localhost:8188 — {exc}")
        return False
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# Full generation test
# ---------------------------------------------------------------------------

async def run_full_generation(prompt: str, dry_run: bool = False) -> bool:
    """
    Run a complete end-to-end generation test.

    Args:
        prompt: The image generation prompt to use.
        dry_run: If True, skip the actual ComfyUI generation call.

    Returns:
        True on success.
    """
    from backend.image_system.brains.router_brain import RouterBrain
    from backend.image_system.services.prompt_builder import PromptBuilder
    from backend.image_system.services.comfyui_client import ComfyUIClient
    from backend.image_system.services.image_reviewer import ImageReviewer
    from backend.image_system.brains.critic_brain import CriticBrain

    _section(f"Full Generation Test — {'DRY RUN' if dry_run else 'LIVE'}")
    print(f"  Prompt: {_col(prompt, _CYAN)}")

    # 1. Route
    print()
    _info("Step 1: Routing...")
    t0 = time.perf_counter()
    router = RouterBrain()
    try:
        route_result = await router.route(prompt)
        elapsed = (time.perf_counter() - t0) * 1000
        _ok(f"Routed in {elapsed:.0f}ms")
        print()
        print("  Route Result:")
        for k, v in route_result.items():
            print(f"    {k:30s}: {v}")
    except Exception as exc:
        _fail(f"Routing failed: {exc}")
        return False

    # 2. Build prompts
    print()
    _info("Step 2: Building prompts...")
    try:
        pb = PromptBuilder()
        prompts = await pb.build(prompt, route_result)
        _ok("Prompts built")
        print(f"    Positive: {prompts['positive'][:120]}...")
        print(f"    Negative: {prompts['negative'][:80]}...")
    except Exception as exc:
        _fail(f"PromptBuilder failed: {exc}")
        return False

    if dry_run:
        # 3. Show what workflow would be generated
        print()
        _info("Step 3: (DRY RUN) Building workflow (not submitting to ComfyUI)...")
        try:
            import json as _json
            from pathlib import Path as _Path
            registry_path = _Path(__file__).parent.parent / "config" / "model_registry.json"
            with open(registry_path) as f:
                registry = _json.load(f)
            ck_key = route_result.get("selected_checkpoint", "anime_general")
            ck_info = registry["image_checkpoints"].get(ck_key, {})
            ck_file = ck_info.get("file", f"{ck_key}.safetensors")
            ck_type = ck_info.get("type", "SD1.5")

            width, height = pb.size_for_visual_mode(
                route_result.get("visual_mode", "portrait"), ck_type
            )
            steps = pb.steps_for_quality("balanced", ck_type)
            cfg = pb.cfg_for_style(route_result.get("style_family", "anime"))

            comfyui = ComfyUIClient()
            workflow = comfyui.build_standard_workflow(
                checkpoint=ck_file,
                positive_prompt=prompts["positive"],
                negative_prompt=prompts["negative"],
                width=width, height=height, steps=steps, cfg=cfg,
            )
            _ok(f"Workflow built: {len(workflow)} nodes, size={width}x{height} steps={steps} cfg={cfg}")
            print(f"\n  Workflow preview (node IDs):\n    {list(workflow.keys())}")
            print()
            _ok("DRY RUN complete. All systems nominal.")
            return True
        except Exception as exc:
            _fail(f"Workflow build failed: {exc}")
            return False

    # 3. Generate
    print()
    _info("Step 3: Generating image via ComfyUI (this may take a while)...")
    try:
        import json as _json
        from pathlib import Path as _Path
        registry_path = _Path(__file__).parent.parent / "config" / "model_registry.json"
        with open(registry_path) as f:
            registry = _json.load(f)
        ck_key = route_result.get("selected_checkpoint", "anime_general")
        ck_info = registry["image_checkpoints"].get(ck_key, {})
        ck_file = ck_info.get("file", f"{ck_key}.safetensors")
        ck_type = ck_info.get("type", "SD1.5")

        width, height = pb.size_for_visual_mode(
            route_result.get("visual_mode", "portrait"), ck_type
        )
        steps = pb.steps_for_quality("balanced", ck_type)
        cfg = pb.cfg_for_style(route_result.get("style_family", "anime"))

        comfyui = ComfyUIClient()
        workflow = comfyui.build_standard_workflow(
            checkpoint=ck_file,
            positive_prompt=prompts["positive"],
            negative_prompt=prompts["negative"],
            width=width, height=height, steps=steps, cfg=cfg,
        )

        t_gen = time.perf_counter()
        images = await comfyui.generate(workflow, timeout=300)
        gen_elapsed = (time.perf_counter() - t_gen) * 1000

        if not images:
            _fail("ComfyUI returned no images")
            return False

        image_bytes = images[0]
        _ok(f"Image generated in {gen_elapsed:.0f}ms ({len(image_bytes)} bytes)")

        # Save to output directory
        ts = int(time.time())
        out_path = OUTPUT_DIR / f"test_output_{ts}.png"
        out_path.write_bytes(image_bytes)
        _ok(f"Saved to: {out_path}")
    except Exception as exc:
        _fail(f"Generation failed: {exc}")
        return False

    # 4. Review
    print()
    _info("Step 4: Reviewing image quality...")
    try:
        reviewer = ImageReviewer()
        review = await reviewer.review_image(image_bytes, prompt, route_result)
        _ok("Review complete")
        print()
        print("  Review Result:")
        for k, v in review.items():
            print(f"    {k:30s}: {v}")
    except Exception as exc:
        _fail(f"Review failed (non-fatal): {exc}")
        review = {}

    # 5. Critic
    print()
    _info("Step 5: Critic evaluation...")
    try:
        critic = CriticBrain()
        critic_result = await critic.evaluate(prompt, route_result, review)
        _ok("Critic evaluation complete")
        print()
        print("  Critic Result:")
        for k, v in critic_result.items():
            print(f"    {k:30s}: {v}")
    except Exception as exc:
        _fail(f"Critic failed (non-fatal): {exc}")
        critic_result = {}

    print()
    _ok("End-to-end test complete.")
    return True


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    parser = argparse.ArgumentParser(description="Mini Assistant image generation test")
    parser.add_argument("--dry-run", action="store_true", help="Skip ComfyUI call")
    parser.add_argument("--prompt", default="draw a shonen anime warrior with lightning aura",
                        help="Prompt to use for generation test")
    parser.add_argument("--skip-checks", action="store_true", help="Skip service availability checks")
    args = parser.parse_args()

    print()
    print(_col("=" * 70, _BOLD))
    print(_col("  Mini Assistant — End-to-End Generation Test", _BOLD))
    print(_col("=" * 70, _BOLD))

    if not args.skip_checks:
        _section("Service Availability Checks")

        _info("Checking Ollama...")
        ollama_ok = await check_ollama()

        _info("Checking required models...")
        model_status = await check_required_models()
        models_ok = any(model_status.values())

        if not args.dry_run:
            _info("Checking ComfyUI...")
            comfyui_ok = await check_comfyui()
        else:
            comfyui_ok = True
            _info("ComfyUI check skipped (dry-run mode)")

        if not ollama_ok:
            print()
            _fail("Ollama is not running. Start it with: ollama serve")
            if not args.dry_run:
                sys.exit(1)

        if not comfyui_ok and not args.dry_run:
            print()
            _fail("ComfyUI is not running. Start it before running this test.")
            sys.exit(1)

    success = await run_full_generation(prompt=args.prompt, dry_run=args.dry_run)

    print()
    print(_col("=" * 70, _BOLD))
    if success:
        print(_col("  ALL TESTS PASSED", _GREEN))
    else:
        print(_col("  SOME TESTS FAILED", _RED))
    print(_col("=" * 70, _BOLD))
    print()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
