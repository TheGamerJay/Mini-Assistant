"""
FastAPI server for the Mini Assistant image system.

Exposes endpoints for image generation, routing, vision analysis, chat,
model management, and health checks.

Run with:
    uvicorn backend.image_system.api.server:app --host 0.0.0.0 --port 7860
"""

import asyncio
import base64
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .models import (
    GenerateRequest,
    GenerateResponse,
    GenerationPlan,
    DryRunResponse,
    RouteRequest,
    AnalyzeRequest,
    ChatRequest,
    PullModelsRequest,
    ModelStatusResponse,
    ErrorResponse,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Mini Assistant Image System",
    description="Local image generation using Ollama brains + ComfyUI",
    version="1.0.0",
)

_CORS_DEFAULTS = ",".join([
    "https://mini-assistant-production.up.railway.app",
    "https://www.miniassistantai.com",
    "https://miniassistantai.com",
    "https://ai.miniassistantai.com",
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    "http://localhost:8080",
])
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", _CORS_DEFAULTS).split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Phase 10: Production middleware stack
# ---------------------------------------------------------------------------
try:
    from mini_assistant.phase10.request_tracer  import attach_tracer
    from mini_assistant.phase10.rate_limiter    import attach_rate_limiter
    from mini_assistant.phase10.auth_middleware import attach_auth
    attach_tracer(app)
    attach_rate_limiter(app)
    attach_auth(app)
    logger.info("✓ Phase 10 middleware stack attached (image_system)")
except Exception as _p10_err:
    logger.warning("Phase 10 middleware unavailable (image_system): %s", _p10_err)

# ---------------------------------------------------------------------------
# Active generation tracking (for cancellation)
# ---------------------------------------------------------------------------

_active_generations: Dict[str, asyncio.Task] = {}

# ---------------------------------------------------------------------------
# Lazy brain / service singletons (created on first use to avoid import errors)
# ---------------------------------------------------------------------------

_router_brain = None
_coding_brain = None
_vision_brain = None
_embed_brain = None
_critic_brain = None
_prompt_builder = None
_comfyui_client = None
_ollama_client = None


def _get_router():
    global _router_brain
    if _router_brain is None:
        from ..brains.router_brain import RouterBrain
        _router_brain = RouterBrain()
    return _router_brain


def _get_coding():
    global _coding_brain
    if _coding_brain is None:
        from ..brains.coding_brain import CodingBrain
        _coding_brain = CodingBrain()
    return _coding_brain


def _get_vision():
    global _vision_brain
    if _vision_brain is None:
        from ..brains.vision_brain import VisionBrain
        _vision_brain = VisionBrain()
    return _vision_brain


def _get_embed():
    global _embed_brain
    if _embed_brain is None:
        from ..brains.embed_brain import EmbedBrain
        _embed_brain = EmbedBrain()
    return _embed_brain


def _get_critic():
    global _critic_brain
    if _critic_brain is None:
        from ..brains.critic_brain import CriticBrain
        _critic_brain = CriticBrain()
    return _critic_brain


def _get_prompt_builder():
    global _prompt_builder
    if _prompt_builder is None:
        from ..services.prompt_builder import PromptBuilder
        _prompt_builder = PromptBuilder()
    return _prompt_builder


def _get_comfyui():
    global _comfyui_client
    if _comfyui_client is None:
        from ..services.comfyui_client import ComfyUIClient
        comfyui_url = os.environ.get("COMFYUI_URL", "http://localhost:8188")
        _comfyui_client = ComfyUIClient(base_url=comfyui_url)
    return _comfyui_client


def _get_ollama():
    global _ollama_client
    if _ollama_client is None:
        from ..services.ollama_client import OllamaClient
        _ollama_client = OllamaClient()
    return _ollama_client


def _load_registry() -> dict:
    import json as _json
    registry_path = Path(__file__).parent.parent / "config" / "model_registry.json"
    with open(registry_path) as f:
        return _json.load(f)


# ---------------------------------------------------------------------------
# Startup event
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup_event():
    """Run availability check at startup and log the report."""
    logger.info("Mini Assistant Image System starting up...")
    try:
        from ..utils.startup_check import run_full_check, print_report
        report = await run_full_check()
        print_report(report)
    except Exception as exc:
        logger.warning("Startup check failed: %s", exc)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health_check():
    """Health check: reports ComfyUI connectivity and checkpoint availability."""
    comfyui_url = os.environ.get("COMFYUI_URL", "http://localhost:8188")
    comfyui_ok = False
    try:
        import httpx as _httpx
        async with _httpx.AsyncClient() as _client:
            r = await _client.get(f"{comfyui_url}/system_stats", timeout=3.0)
            comfyui_ok = r.status_code == 200
    except Exception:
        pass

    # Check for installed checkpoints
    checkpoints_dir = Path(os.environ.get(
        "COMFYUI_CHECKPOINTS_DIR",
        "C:/Users/jaaye/ai-panels/ComfyUI/models/checkpoints"
    ))
    checkpoint_files = []
    checkpoints_ok = False
    if checkpoints_dir.exists():
        checkpoint_files = [f.name for f in checkpoints_dir.iterdir()
                            if f.suffix in (".safetensors", ".ckpt", ".pt")]
        checkpoints_ok = len(checkpoint_files) > 0

    status = {
        "status": "ok",
        "service": "mini-assistant-image-system",
        "comfyui": "connected" if comfyui_ok else "disconnected",
        "checkpoints": {
            "available": checkpoints_ok,
            "count": len(checkpoint_files),
            "message": None if checkpoints_ok else "No checkpoint models found. Place .safetensors files in ComfyUI/models/checkpoints/",
        },
    }
    return status


@app.post("/api/image/route")
async def route_only(req: RouteRequest):
    """
    Classify a prompt and return the routing decision without generating an image.
    Useful for debugging the router.
    """
    from ..utils.routing_guard import validate_route as guard_validate
    try:
        route_result = await _get_router().route(req.prompt)
        route_result = guard_validate(route_result)
        return {"route_result": route_result}
    except Exception as exc:
        logger.error("Route endpoint error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@app.delete("/api/image/generate/{session_id}", status_code=200)
async def cancel_generation(session_id: str):
    """Cancel an in-progress generation by session_id."""
    task = _active_generations.get(session_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"No active generation for session '{session_id}'")
    task.cancel()
    _active_generations.pop(session_id, None)
    logger.info("Generation cancelled: session_id=%s", session_id)
    return {"cancelled": True, "session_id": session_id}


@app.post("/api/image/generate")
async def generate_image(req: GenerateRequest):
    """
    Full image generation pipeline:
    1. Prompt safety validation.
    2. RouterBrain classifies the request (with routing_guard confidence + compatibility checks).
    3. Apply any manual overrides.
    4. If dry_run, return the plan without generating.
    5. PromptBuilder crafts positive + negative prompts.
    6. ComfyUIClient generates the image (with timeout + cancellation).
    7. ImageReviewer scores the result (unless quality=='fast').
    8. CriticBrain evaluates; retries once if warranted.
    9. EmbedBrain stores successful routes for memory.
    10. Metadata sidecar saved beside the output image.
    """
    from ..utils.prompt_safety import validate as ps_validate
    from ..utils.routing_guard import validate_route as guard_validate
    from ..utils import image_logger, metadata_writer

    session_id = req.session_id or str(uuid.uuid4())
    start_time = time.perf_counter()

    # ---- Step 1: Prompt safety ----
    is_valid, clean_prompt, safety_error = ps_validate(req.prompt)
    if not is_valid:
        raise HTTPException(status_code=400, detail=f"Prompt rejected: {safety_error}")
    prompt_warnings = []
    if clean_prompt != req.prompt:
        prompt_warnings.append("Prompt was sanitized (whitespace/control chars removed).")

    # ---- Step 2: Route ----
    reference_bytes = None
    mask_bytes      = None
    pose_bytes      = None
    style_bytes     = None
    if req.reference_image_base64:
        try:
            reference_bytes = base64.b64decode(req.reference_image_base64)
        except Exception:
            logger.warning("Could not decode reference_image_base64")
    if req.mask_image_base64:
        try:
            mask_bytes = base64.b64decode(req.mask_image_base64)
        except Exception:
            logger.warning("Could not decode mask_image_base64")
    if req.pose_image_base64:
        try:
            pose_bytes = base64.b64decode(req.pose_image_base64)
        except Exception:
            logger.warning("Could not decode pose_image_base64")
    if req.style_image_base64:
        try:
            style_bytes = base64.b64decode(req.style_image_base64)
        except Exception:
            logger.warning("Could not decode style_image_base64")

    try:
        route_result = await _get_router().route(clean_prompt, reference_image=reference_bytes)
        route_result = guard_validate(route_result)
    except Exception as exc:
        logger.error("Routing failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Routing error: {exc}")

    # Log routing decision
    elapsed_route = (time.perf_counter() - start_time) * 1000
    image_logger.log_router_decision(clean_prompt, route_result, elapsed_route, session_id)

    if route_result.get("_low_confidence_warning"):
        prompt_warnings.append(route_result["_low_confidence_warning"])
    if route_result.get("_compatibility_warning"):
        prompt_warnings.append(route_result["_compatibility_warning"])

    intent = route_result.get("intent", "chat")

    # ---- Step 2b: ComfyUI mode routing (Phase 7) ----
    from ..services.comfyui_router import route_image_request as _comfy_route
    comfy_decision = _comfy_route(
        prompt=clean_prompt,
        reference_image=req.reference_image_base64,
        mask_image=req.mask_image_base64,
        pose_image=req.pose_image_base64,
        style_image=req.style_image_base64,
    )
    logger.info(
        "ComfyUI route: mode=%s target_tab=%s reason=%s",
        comfy_decision.mode, comfy_decision.target_tab, comfy_decision.reason,
    )

    # ---- Step 3: Non-image intents ----
    if intent in ("chat", "planning"):
        ollama = _get_ollama()
        try:
            from ..services.ollama_client import _model_name
            reply = await ollama.run_prompt(
                model=_model_name("router"),
                prompt=clean_prompt,
                temperature=0.7,
            )
        except Exception as exc:
            reply = f"I'm having trouble responding right now: {exc}"

        elapsed = (time.perf_counter() - start_time) * 1000
        return GenerateResponse(
            image_base64=None,
            route_result={**route_result, "text_reply": reply},
            review=None,
            retry_used=False,
            critic_result=None,
            session_id=session_id,
            generation_time_ms=round(elapsed, 1),
            prompt_warnings=prompt_warnings,
        )

    if intent == "coding":
        coding = _get_coding()
        try:
            reply = await coding.run(clean_prompt)
        except Exception as exc:
            reply = f"Coding brain error: {exc}"

        elapsed = (time.perf_counter() - start_time) * 1000
        return GenerateResponse(
            image_base64=None,
            route_result={**route_result, "text_reply": reply},
            review=None,
            retry_used=False,
            critic_result=None,
            session_id=session_id,
            generation_time_ms=round(elapsed, 1),
            prompt_warnings=prompt_warnings,
        )

    # ---- Step 4: Image generation setup ----
    # Apply checkpoint/workflow overrides
    checkpoint_key = req.override_checkpoint or route_result.get("selected_checkpoint", "anime_general")
    workflow_key = req.override_workflow or route_result.get("selected_workflow", "anime_general")
    quality = req.quality or "balanced"

    # Load checkpoint file from registry
    try:
        registry = _load_registry()
        checkpoint_info = registry["image_checkpoints"].get(checkpoint_key, {})
        checkpoint_file = checkpoint_info.get("file", f"{checkpoint_key}.safetensors")
        checkpoint_type = checkpoint_info.get("type", "SD1.5")
    except Exception:
        checkpoint_file = f"{checkpoint_key}.safetensors"
        checkpoint_type = "SD1.5"

    # Build prompts
    try:
        pb = _get_prompt_builder()
        prompts = await pb.build(clean_prompt, route_result)
        positive_prompt = prompts["positive"]
        negative_prompt = prompts["negative"]
        width = req.override_width or 0
        height = req.override_height or 0
        if not (width and height):
            width, height = pb.size_for_visual_mode(
                route_result.get("visual_mode", "portrait"), checkpoint_type, quality
            )
        steps = req.override_steps or pb.steps_for_quality(quality, checkpoint_type)
        cfg = req.override_cfg or pb.cfg_for_style(route_result.get("style_family", "anime"))
        seed = req.override_seed
    except Exception as exc:
        logger.error("PromptBuilder failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Prompt build error: {exc}")

    # Collect which overrides were applied
    overrides_applied: Dict[str, Any] = {}
    for field in ("checkpoint", "workflow", "width", "height", "steps", "cfg", "seed"):
        attr = f"override_{field}"
        val = getattr(req, attr, None)
        if val is not None:
            overrides_applied[field] = val

    plan = GenerationPlan(
        checkpoint=checkpoint_key,
        checkpoint_file=checkpoint_file,
        workflow=workflow_key,
        positive_prompt=positive_prompt,
        negative_prompt=negative_prompt,
        width=width,
        height=height,
        steps=steps,
        cfg=cfg,
        seed=seed,
        quality=quality,
        overrides_applied=overrides_applied,
    )

    # ---- Step 5: Dry run — return plan without generating ----
    if req.dry_run:
        elapsed = (time.perf_counter() - start_time) * 1000
        return DryRunResponse(
            session_id=session_id,
            route_result=route_result,
            plan=plan,
            prompt_warnings=prompt_warnings,
        )

    # ---- Step 6: ComfyUI generation (with timeout + cancellation) ----
    comfyui = _get_comfyui()

    # ---- Step 6a: Build workflow based on ComfyUI routing mode ----
    from ..services.comfyui_router import WORKFLOW_GENERATE
    if comfy_decision.workflow == WORKFLOW_GENERATE or not any([reference_bytes, mask_bytes, pose_bytes, style_bytes]):
        # Standard text-to-image
        workflow = comfyui.build_standard_workflow(
            checkpoint=checkpoint_file,
            positive_prompt=positive_prompt,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            steps=steps,
            cfg=cfg,
            seed=seed,
        )
    else:
        # Reference-guided or edit/inpaint — load JSON workflow + upload images
        try:
            workflow = comfyui.load_workflow(comfy_decision.workflow)
            # Inject text params first
            workflow = comfyui.inject_params(workflow, {
                "checkpoint":       checkpoint_file,
                "positive_prompt":  positive_prompt,
                "negative_prompt":  negative_prompt,
                "steps":            steps,
                "cfg":              cfg,
                "seed":             seed if seed is not None else __import__("random").randint(0, 2**32 - 1),
                "denoise":          req.denoise_strength if req.denoise_strength is not None else 0.75,
            })

            # Upload images and inject filenames into LoadImage nodes
            # Primary reference image (reference mode) or init image (edit mode)
            primary_img = reference_bytes or pose_bytes or style_bytes
            if primary_img:
                stored_name = await comfyui.upload_image(primary_img, "reference_input.png")
                workflow = comfyui.inject_params(workflow, {"init_image_filename": stored_name})

            # Mask image (edit/inpaint mode)
            if mask_bytes:
                mask_name = await comfyui.upload_image(mask_bytes, "mask_input.png")
                workflow = comfyui.inject_params(workflow, {"mask_image_filename": mask_name})

        except Exception as exc:
            logger.error("Workflow load/inject failed (%s) — falling back to standard workflow", exc)
            workflow = comfyui.build_standard_workflow(
                checkpoint=checkpoint_file,
                positive_prompt=positive_prompt,
                negative_prompt=negative_prompt,
                width=width,
                height=height,
                steps=steps,
                cfg=cfg,
                seed=seed,
            )

    image_bytes: Optional[bytes] = None
    review: Optional[dict] = None
    critic_result: Optional[dict] = None
    retry_used = False
    gen_start = time.perf_counter()

    try:
        gen_task = asyncio.ensure_future(comfyui.generate(workflow, timeout=300))
        _active_generations[session_id] = gen_task
        try:
            images = await gen_task
            image_bytes = images[0] if images else None
        except asyncio.CancelledError:
            logger.info("Generation cancelled: session_id=%s", session_id)
            raise HTTPException(status_code=499, detail="Generation cancelled by client")
        finally:
            _active_generations.pop(session_id, None)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("ComfyUI generation failed: %s", exc, exc_info=True)
        gen_elapsed = (time.perf_counter() - gen_start) * 1000
        image_logger.log_comfyui_execution(
            session_id, checkpoint_key, workflow_key,
            width, height, steps, cfg, seed or -1,
            gen_elapsed, None, error=str(exc),
        )
        raise HTTPException(status_code=502, detail=f"ComfyUI error: {exc}")

    gen_elapsed = (time.perf_counter() - gen_start) * 1000
    image_logger.log_comfyui_execution(
        session_id, checkpoint_key, workflow_key,
        width, height, steps, cfg, seed or -1,
        gen_elapsed, None,
    )

    # ---- Step 7: Review (skip for fast quality) ----
    review_start = time.perf_counter()
    if image_bytes and quality != "fast":
        try:
            from ..services.image_reviewer import ImageReviewer
            reviewer = ImageReviewer()
            review = await reviewer.review_image(image_bytes, clean_prompt, route_result)
        except Exception as exc:
            logger.warning("Image review failed: %s", exc)
            review = None

    # ---- Step 8: Critic evaluation + single retry ----
    if review and image_bytes:
        try:
            critic = _get_critic()
            critic_result = await critic.evaluate(clean_prompt, route_result, review)

            if critic_result.get("should_retry"):
                adjusted = critic_result.get("adjusted_params", {})
                alt_checkpoint_key = critic_result.get("alt_checkpoint") or checkpoint_key
                try:
                    registry = _load_registry()
                    checkpoint_info_retry = registry["image_checkpoints"].get(alt_checkpoint_key, {})
                    retry_checkpoint_file = checkpoint_info_retry.get("file", checkpoint_file)
                except Exception:
                    retry_checkpoint_file = checkpoint_file

                retry_workflow = comfyui.build_standard_workflow(
                    checkpoint=retry_checkpoint_file,
                    positive_prompt=positive_prompt,
                    negative_prompt=negative_prompt,
                    width=width,
                    height=height,
                    steps=adjusted.get("steps", steps),
                    cfg=adjusted.get("cfg", cfg),
                    seed=adjusted.get("seed"),
                )

                retry_images = await comfyui.generate(retry_workflow, timeout=300)
                if retry_images:
                    image_bytes = retry_images[0]
                    retry_used = True
                    logger.info("Retry completed with checkpoint=%s", alt_checkpoint_key)
        except Exception as exc:
            logger.warning("Critic/retry failed: %s", exc)

    review_elapsed = (time.perf_counter() - review_start) * 1000
    quality_score = review.get("quality_score", 0.7) if review else 0.7
    image_logger.log_review_event(
        session_id, quality_score, retry_used,
        review.get("retry_reason") if review else None,
        critic_result.get("alt_checkpoint") if critic_result else None,
        2 if retry_used else 1,
        review_elapsed,
        None,
    )

    # ---- Step 9: Store successful route ----
    if image_bytes and quality_score >= 0.5:
        try:
            await _get_embed().store_successful_route(clean_prompt, route_result, quality_score)
        except Exception as exc:
            logger.warning("EmbedBrain store failed: %s", exc)

    # ---- Step 10: Save image + metadata sidecar ----
    out_path = None
    if image_bytes:
        try:
            out_path = metadata_writer.save_output_image(image_bytes, session_id, seed or -1)
            meta = metadata_writer.build_metadata(
                original_prompt=req.prompt,
                positive_prompt=positive_prompt,
                negative_prompt=negative_prompt,
                route=route_result,
                checkpoint=checkpoint_key,
                workflow=workflow_key,
                seed=seed or -1,
                width=width,
                height=height,
                steps=steps,
                cfg=cfg,
                quality=quality,
                review_result=review,
                session_id=session_id,
                generation_ms=(time.perf_counter() - start_time) * 1000,
            )
            metadata_writer.save_metadata(out_path, meta)
        except Exception as exc:
            logger.warning("Metadata/image save failed: %s", exc)

    elapsed = (time.perf_counter() - start_time) * 1000
    image_b64 = base64.b64encode(image_bytes).decode("utf-8") if image_bytes else None

    return GenerateResponse(
        image_base64=image_b64,
        route_result={**route_result, "comfyui_mode": comfy_decision.mode, "target_tab": comfy_decision.target_tab},
        review=review,
        retry_used=retry_used,
        critic_result=critic_result,
        session_id=session_id,
        generation_time_ms=round(elapsed, 1),
        prompt_warnings=prompt_warnings,
    )


@app.post("/api/image/analyze")
async def analyze_image(req: AnalyzeRequest):
    """
    Analyse an image using the vision brain.

    Body: { image_base64: str, question?: str }
    """
    try:
        image_bytes = base64.b64decode(req.image_base64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 image data")

    try:
        vision = _get_vision()
        answer = await vision.analyze(image_bytes, req.question or "Describe this image.")
        return {"answer": answer}
    except Exception as exc:
        logger.error("Vision analysis failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """
    Multi-purpose chat endpoint — Phase 2: Full Executive Hierarchy.

    Request flow:
      Command Parser  → slash command detection
      Planner         → intent + task list  (ALWAYS FIRST)
      CEO             → posture: mode, risk, priority
      Manager         → session context, normalization
      Supervisor      → task state tracking
      Brain           → image gen / coding / chat execution
      Critic          → reply validation
      Composer        → final response assembly

    Slash commands (/fix, /image, /code, etc.) override intent detection.
    Phase 2 adds CEO posture, Manager session context, and Supervisor task tracking.
    """
    from ..utils.prompt_safety import validate as ps_validate

    session_id = req.session_id or str(uuid.uuid4())

    is_valid, clean_message, safety_error = ps_validate(req.message)
    if not is_valid:
        raise HTTPException(status_code=400, detail=f"Message rejected: {safety_error}")

    # Decode user-attached image (Phase 5)
    attached_image_bytes: Optional[bytes] = None
    if req.image_base64:
        try:
            attached_image_bytes = base64.b64decode(req.image_base64)
        except Exception:
            logger.warning("Could not decode attached image_base64 — ignoring.")

    # ── Phase 1 Step 1: Command Parser ─────────────────────────────────────────
    phase1_plan        = None
    phase1_critic      = None
    parsed_cmd         = None
    effective_msg      = clean_message
    ceo_posture        = None
    manager_packet     = None
    supervisor_result  = None
    skill_match        = None
    reflection_record  = None
    parallel_result    = None
    mission_result     = None
    engineering_ctx    = None   # Phase 6
    memory_facts_stored = []    # Phase 6

    try:
        from mini_assistant.phase1.command_parser import parse as cmd_parse
        from mini_assistant.phase1.intent_planner import plan as make_plan
        from mini_assistant.phase1.critic import critique
        from mini_assistant.phase1.composer import compose as phase1_compose
        from mini_assistant.phase1.command_parser import help_text

        # Parse slash command (if any)
        parsed_cmd  = cmd_parse(clean_message)
        effective_msg = parsed_cmd.args if parsed_cmd.is_slash else clean_message

        # ── Phase 1 Step 2: Planner (ALWAYS RUNS FIRST) ────────────────────────
        # If an image is attached, force image_analysis intent regardless of text
        from mini_assistant.phase1.command_parser import ParsedCommand as _PC, SLASH_COMMANDS as _SC
        if attached_image_bytes and not (parsed_cmd and parsed_cmd.is_slash):
            # Synthesise a /analyze slash command so Planner locks to image_analysis
            parsed_cmd = _PC(
                raw=effective_msg,
                command="analyze",
                args=effective_msg,
                intent_override="image_analysis",
                is_slash=True,
                is_known=True,
                help_requested=False,
            )

        phase1_plan = make_plan(
            message        = effective_msg,
            parsed_command = parsed_cmd,
            history        = req.history or [],
        )
        logger.info(
            "Planner → intent=%s confidence=%.2f method=%s ms=%.1f",
            phase1_plan.intent, phase1_plan.confidence,
            phase1_plan.routing_method, phase1_plan.planner_ms,
        )

        # /help shortcut — return command list without hitting any brain
        if parsed_cmd.help_requested:
            return phase1_compose(
                reply        = help_text(),
                plan         = phase1_plan,
                critic       = critique(help_text(), phase1_plan),
                session_id   = session_id,
                route_result = {},
            )

        # ── Phase 2 Step 1: CEO — set posture ──────────────────────────────────
        try:
            from mini_assistant.phase2.ceo import assess as ceo_assess
            ceo_posture = ceo_assess(phase1_plan, effective_msg)
            logger.info(
                "CEO → mode=%s risk=%s priority=%s ms=%.1f",
                ceo_posture.mode, ceo_posture.risk_posture,
                ceo_posture.priority, ceo_posture.ceo_ms,
            )
        except Exception as _ceo_err:
            logger.warning("CEO failed (%s) — using defaults.", _ceo_err)
            ceo_posture = None

        # ── Phase 2 Step 2: Manager — normalize + inject session context ───────
        try:
            from mini_assistant.phase2.manager import prepare as mgr_prepare
            history_list = [{"role": h.role, "content": h.content} for h in (req.history or [])]
            manager_packet = mgr_prepare(
                message    = effective_msg,
                session_id = session_id,
                plan       = phase1_plan,
                posture    = ceo_posture,
                history    = history_list,
            )
            logger.info(
                "Manager → turn=%d is_continuation=%s ceo_mode=%s ms=%.1f",
                manager_packet.session_context.get("turn_count", 0),
                manager_packet.is_continuation,
                manager_packet.ceo_mode,
                manager_packet.manager_ms,
            )
        except Exception as _mgr_err:
            logger.warning("Manager failed (%s) — skipping context injection.", _mgr_err)
            manager_packet = None

        # ── Phase 3 Step 1: Skill Selector ─────────────────────────────────────
        try:
            from mini_assistant.phase3.skill_selector import get_selector
            skill_match = get_selector().select(
                plan          = phase1_plan,
                message       = effective_msg,
                slash_command = parsed_cmd.command if parsed_cmd and parsed_cmd.is_slash else None,
            )
            if skill_match.matched:
                logger.info(
                    "SkillSelector matched: %s (conf=%.2f, %d steps) ms=%.1f",
                    skill_match.skill.name, skill_match.confidence,
                    len(skill_match.override_steps), skill_match.selector_ms,
                )
            else:
                logger.debug("SkillSelector: no match (ms=%.1f)", skill_match.selector_ms)
        except Exception as _ss_err:
            logger.warning("SkillSelector failed (%s) — continuing without skill.", _ss_err)
            skill_match = None

        # ── Phase 2 Step 3: Supervisor — sequential task state tracking ────────
        try:
            from mini_assistant.phase2.supervisor import Supervisor
            if manager_packet:
                supervisor = Supervisor(manager_packet)
                # If a skill matched, use its refined steps; otherwise use Planner's
                tasks_to_run = (
                    skill_match.override_steps
                    if skill_match and skill_match.matched and skill_match.override_steps
                    else phase1_plan.sequential_tasks
                )
                supervisor_result = supervisor.supervise(tasks_to_run)
                logger.info(
                    "Supervisor → %d/%d tasks completed, overall=%s ms=%.1f",
                    len(supervisor_result.completed_tasks),
                    len(supervisor_result.tasks),
                    supervisor_result.overall_state,
                    supervisor_result.supervisor_ms,
                )
            else:
                supervisor_result = None
        except Exception as _sup_err:
            logger.warning("Supervisor failed (%s) — continuing without task tracking.", _sup_err)
            supervisor_result = None

        # ── Phase 4 Step 1: Parallel Supervisor — wave-based async execution ───
        try:
            from mini_assistant.phase4.parallel_supervisor import ParallelSupervisor
            parallel_tasks = phase1_plan.parallel_tasks or []
            if parallel_tasks:
                par_sup = ParallelSupervisor()
                parallel_result = await par_sup.run(parallel_tasks)
                logger.info(
                    "ParallelSupervisor → %d tasks in %d waves, %.1f ms (gain=%.1fms)",
                    parallel_result.tasks_total,
                    len(parallel_result.waves),
                    parallel_result.total_ms,
                    parallel_result.parallel_gain,
                )
        except Exception as _par_err:
            logger.warning("ParallelSupervisor failed (%s) — non-fatal.", _par_err)
            parallel_result = None

    except Exception as _p1_err:
        logger.warning("Phase 1/2 pipeline failed (%s) — falling back to legacy routing.", _p1_err)
        phase1_plan = None
        ceo_posture = None
        manager_packet = None
        supervisor_result = None

    # ── Phase 1 Step 3: Execution Router ───────────────────────────────────────
    # Use Planner's execution_intent to drive the existing image_system router.
    # If Planner is unavailable, fall back to the RouterBrain as before.

    execution_intent = (
        phase1_plan.execution_intent if phase1_plan else None
    )
    route_result: dict = {}

    # For image generation, still run the RouterBrain to get checkpoint/workflow detail
    if execution_intent == "image_generation" or execution_intent is None:
        try:
            from ..utils.routing_guard import validate_route as guard_validate
            rr = await _get_router().route(effective_msg)
            rr = guard_validate(rr)
            route_result = rr if isinstance(rr, dict) else (rr.dict() if hasattr(rr, "dict") else {})
            if execution_intent is None:
                execution_intent = route_result.get("intent", "chat")
        except Exception as exc:
            logger.error("RouterBrain failed: %s", exc)
            route_result     = {"intent": "chat"}
            execution_intent = execution_intent or "chat"

    # ── Phase 9 Step 1: Self-Improvement Context Injection ──────────────────────
    phase9_ctx = None
    try:
        from mini_assistant.phase9.context_injector import get_injector
        phase9_ctx = get_injector().build(
            intent     = execution_intent or "chat",
            session_id = session_id,
        )
        if phase9_ctx.sources:
            logger.info(
                "Phase9Injector: lessons=%d memory=%d (%.1f ms)",
                phase9_ctx.lessons_used, phase9_ctx.memory_facts_used, phase9_ctx.assembly_ms,
            )
    except Exception as _p9_err:
        logger.debug("Phase9 context injection failed (non-fatal): %s", _p9_err)

    # ── Phase 6 Step 1: Engineering Assistant context assembly ──────────────────
    try:
        from mini_assistant.phase6.engineering_assistant import get_engineering_assistant
        engineering_ctx = get_engineering_assistant().build(
            intent     = phase1_plan.intent if phase1_plan else "normal_chat",
            message    = effective_msg,
            session_id = session_id,
        )
        if engineering_ctx.sources_used:
            logger.info(
                "EngineeringAssistant: %s (%.1f ms)",
                engineering_ctx.sources_used, engineering_ctx.assembly_ms,
            )
    except Exception as _eng_err:
        logger.debug("EngineeringAssistant failed (non-fatal): %s", _eng_err)
        engineering_ctx = None

    # ── Phase 1 Step 4: Brain Execution ────────────────────────────────────────
    reply = ""

    # Model override from request (Phase 6 model selector)
    from ..services.ollama_client import _model_name as _reg_model_name
    _active_model = req.preferred_model or _reg_model_name("router")

    if execution_intent in ("image_generation", "image_edit"):
        gen_req = GenerateRequest(prompt=effective_msg, session_id=session_id)
        image_response = await generate_image(gen_req)
        # Image generation returns its own response — inject plan metadata and return
        if isinstance(image_response, dict):
            image_response["plan"]         = phase1_plan.to_dict() if phase1_plan else {}
            image_response["intent"]       = "image_generate"
            image_response["slash_command"]= parsed_cmd.command if parsed_cmd and parsed_cmd.is_slash else None
        return image_response

    elif execution_intent == "image_analysis" or (execution_intent == "chat" and attached_image_bytes):
        # User attached an image — route to vision brain
        try:
            vision = _get_vision()
            question = effective_msg or "Describe this image in detail."
            reply = await vision.analyze(attached_image_bytes, question)
        except Exception as exc:
            reply = f"Vision brain error: {exc}"

    elif execution_intent == "coding":
        try:
            # Inject engineering context prefix if available
            eng_prefix = (engineering_ctx.system_prefix if engineering_ctx else "")
            reply = await _get_coding().run(eng_prefix + effective_msg if eng_prefix else effective_msg)
        except Exception as exc:
            reply = f"Coding brain error: {exc}"

    elif execution_intent in ("tool_use", "code_runner", "shell"):
        # ── Phase 8: Tool Brain ─────────────────────────────────────────────
        # Parse "TOOL:<tool_name> CMD:<command>" pattern from message,
        # or route the raw message to shell_safe as a read-only shell command.
        try:
            from mini_assistant.phase8.tool_brain import tool_brain
            from mini_assistant.phase8.security_brain import evaluate_tool

            import re as _re
            _m = _re.search(r"TOOL:(\S+)\s+CMD:(.*)", effective_msg, _re.DOTALL)
            if _m:
                _tool_name = _m.group(1).strip()
                _command   = _m.group(2).strip()
            else:
                _tool_name = "shell_safe"
                _command   = effective_msg

            sec = evaluate_tool(_tool_name, _command)
            if sec.blocked:
                reply = f"⛔ Blocked: {'; '.join(sec.reasons)}"
            elif sec.requires_approval:
                from mini_assistant.phase8.approval_store import approval_store
                aid = approval_store.add_pending(
                    tool_name  = _tool_name,
                    command    = _command,
                    session_id = session_id,
                    risk_level = sec.risk_level,
                    reasons    = sec.reasons,
                )
                reply = (
                    f"⚠️ This action requires approval before it runs.\n\n"
                    f"**Tool:** `{_tool_name}`\n"
                    f"**Command:** `{_command}`\n"
                    f"**Risk:** {sec.risk_level}\n\n"
                    f"Approval ID: `{aid}`"
                )
            else:
                result = await tool_brain.execute(
                    tool_name       = _tool_name,
                    command         = _command,
                    session_id      = session_id,
                    auto_approve_safe = True,
                )
                if result.status == "success":
                    reply = f"```\n{result.output or '(no output)'}\n```"
                else:
                    reply = f"❌ Error (exit {result.exit_code}):\n```\n{result.error or result.output}\n```"
        except Exception as exc:
            reply = f"Tool brain error: {exc}"

    else:
        # General chat / research / planning / file_analysis / web_search
        try:
            ollama_client = _get_ollama()

            # Engineering context covers file_analysis + app_builder + code_runner
            # Fall back to legacy project context for plain file_analysis without engineering ctx
            system_prefix = engineering_ctx.system_prefix if engineering_ctx and engineering_ctx.system_prefix else ""
            if not system_prefix and phase1_plan and phase1_plan.intent == "file_analysis":
                try:
                    from mini_assistant.scanner import get_context
                    ctx = get_context()
                    feat_names = [f["feature"] for f in ctx.to_dict().get("feature_map", [])]
                    warnings   = ctx.to_dict().get("warnings", [])[:3]
                    system_prefix = (
                        f"[PROJECT CONTEXT — {len(feat_names)} features mapped. "
                        f"Key warnings: {'; '.join(warnings) if warnings else 'none'}]\n\n"
                    )
                except Exception:
                    pass

            history_msgs: list[dict] = []
            if req.history:
                for h in req.history[-10:]:
                    history_msgs.append({"role": h.role, "content": h.content})

            # Prepend Phase 9 self-improvement context (lessons + long-term memory)
            phase9_prefix = phase9_ctx.prefix if phase9_ctx else ""
            combined_prefix = phase9_prefix + (system_prefix or "")
            user_content = (combined_prefix + effective_msg) if combined_prefix else effective_msg
            history_msgs.append({"role": "user", "content": user_content})

            reply = await ollama_client.run_chat(
                model       = _active_model,
                messages    = history_msgs,
                temperature = 0.7,
            )
        except Exception as exc:
            reply = f"I'm having trouble responding right now: {exc}"

    # ── Phase 1+2 Step 5: Critic + Composer ────────────────────────────────────
    if phase1_plan is not None:
        try:
            from mini_assistant.phase1.critic import critique
            from mini_assistant.phase1.composer import compose as phase1_compose
            critic_result = critique(reply, phase1_plan)

            # ── Phase 3 Step 2: Reflection (after Critic, before Composer) ─────
            try:
                from mini_assistant.phase3.reflection_layer import reflect
                reflection_record = reflect(
                    message     = effective_msg,
                    plan        = phase1_plan,
                    critic      = critic_result,
                    skill_match = skill_match,
                    reply       = reply,
                )
                logger.debug(
                    "Reflection logged=%s lesson=%s ms=%.1f",
                    reflection_record.logged,
                    reflection_record.lesson[:60],
                    reflection_record.reflection_ms,
                )
            except Exception as _ref_err:
                logger.warning("Reflection failed (non-fatal): %s", _ref_err)
                reflection_record = None

            # ── Phase 9 Step 2: Feed reflection lesson into LearningBrain ─────
            try:
                from mini_assistant.phase9.learning_brain import get_learning_brain
                if reflection_record and reflection_record.lesson:
                    get_learning_brain().record_reflection(
                        lesson       = reflection_record.lesson,
                        intent       = phase1_plan.intent if phase1_plan else "chat",
                        quality_score= getattr(reflection_record, "quality_score", 0.7),
                        success      = True,
                        source       = "reflection",
                    )
            except Exception as _lb_err:
                logger.debug("LearningBrain feed failed (non-fatal): %s", _lb_err)

            # ── Phase 6 Step 2: Session Memory extraction (after reply known) ───
            try:
                from mini_assistant.phase6.session_memory import get_memory
                memory_facts_stored = get_memory().extract_and_store(
                    message    = effective_msg,
                    reply      = reply,
                    session_id = session_id,
                    intent     = phase1_plan.intent if phase1_plan else "normal_chat",
                )
                if memory_facts_stored:
                    logger.info(
                        "SessionMemory: stored %d facts for session %s",
                        len(memory_facts_stored), session_id[:8],
                    )
            except Exception as _mem_err:
                logger.debug("SessionMemory extraction failed (non-fatal): %s", _mem_err)
                memory_facts_stored = []

            # ── Phase 4 Step 2: Mission Manager (after Reflection) ─────────────
            try:
                from mini_assistant.phase4.mission_manager import get_mission_manager
                mission_result = get_mission_manager().process(
                    message    = effective_msg,
                    plan       = phase1_plan,
                    critic     = critic_result,
                    session_id = session_id,
                )
                if mission_result.action != "none":
                    logger.info(
                        "MissionManager → action=%s mission=%s continuation=%s",
                        mission_result.action,
                        mission_result.mission.id[:8] if mission_result.mission else "—",
                        mission_result.is_continuation,
                    )
            except Exception as _mis_err:
                logger.warning("MissionManager failed (non-fatal): %s", _mis_err)
                mission_result = None

            response = phase1_compose(
                reply        = reply,
                plan         = phase1_plan,
                critic       = critic_result,
                session_id   = session_id,
                route_result = route_result,
            )
            # Enrich with Phase 2+3 executive metadata
            if ceo_posture:
                response["ceo"] = ceo_posture.to_dict()
            if manager_packet:
                response["manager"] = manager_packet.to_dict()
            if supervisor_result:
                response["supervisor"] = supervisor_result.to_dict()
            if skill_match:
                response["skill"] = skill_match.to_dict()
            if reflection_record:
                response["reflection"] = reflection_record.to_dict()
            if parallel_result:
                response["parallel"] = parallel_result.to_dict()
            if mission_result and mission_result.action != "none":
                response["mission"] = mission_result.to_dict()
            if engineering_ctx and engineering_ctx.sources_used:
                response["engineering"] = engineering_ctx.to_dict()
            if memory_facts_stored:
                response["memory_stored"] = [
                    {"key": f.key, "value": f.value, "confidence": f.confidence}
                    for f in memory_facts_stored
                ]
            if phase9_ctx and phase9_ctx.sources:
                response["self_improvement"] = phase9_ctx.to_dict()
            response["model_used"] = _active_model
            return response
        except Exception as _c_err:
            logger.warning("Phase 1+2 Critic/Composer failed (%s) — returning raw reply.", _c_err)

    # Legacy fallback response shape (Phase 1 unavailable)
    return {
        "reply":        reply,
        "intent":       execution_intent,
        "route_result": route_result,
        "session_id":   session_id,
    }


@app.get("/api/models/status")
async def models_status():
    """Check which Ollama models are available locally."""
    ollama = _get_ollama()
    try:
        available = await ollama.list_models()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Ollama unreachable: {exc}")

    try:
        registry = _load_registry()
        required_models = {k: v["model"] for k, v in registry["ollama_models"].items()}
    except Exception:
        required_models = {}

    status = {}
    for role, model_name in required_models.items():
        normalised = {m.split(":")[0] for m in available} | set(available)
        status[role] = {
            "model": model_name,
            "available": model_name in normalised or model_name.split(":")[0] in normalised,
        }

    return {"available_models": available, "required_status": status}


@app.post("/api/models/pull")
async def pull_models(req: PullModelsRequest):
    """Pull missing Ollama models. This is a long-running operation."""
    ollama = _get_ollama()
    results = {}
    for model in req.models:
        try:
            await ollama.ensure_models([model])
            results[model] = "pulled"
        except Exception as exc:
            results[model] = f"error: {exc}"
    return {"results": results}
