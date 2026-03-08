"""
FastAPI server for the Mini Assistant image system.

Exposes endpoints for image generation, routing, vision analysis, chat,
model management, and health checks.

Run with:
    uvicorn backend.image_system.api.server:app --host 0.0.0.0 --port 7860
"""

import base64
import logging
import time
import uuid
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Mini Assistant Image System",
    description="Local image generation using Ollama brains + ComfyUI",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://localhost:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Request logging middleware
# ---------------------------------------------------------------------------

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = (time.perf_counter() - start) * 1000
    logger.info(
        "%s %s → %d (%.0fms)",
        request.method, request.url.path, response.status_code, elapsed,
    )
    return response

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
        _comfyui_client = ComfyUIClient()
    return _comfyui_client


def _get_ollama():
    global _ollama_client
    if _ollama_client is None:
        from ..services.ollama_client import OllamaClient
        _ollama_client = OllamaClient()
    return _ollama_client

# ---------------------------------------------------------------------------
# Startup event
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup_event():
    """Check that critical Ollama models are reachable at startup."""
    logger.info("Mini Assistant Image System starting up...")
    ollama = _get_ollama()
    try:
        models = await ollama.list_models()
        logger.info("Ollama available models: %s", models)
    except Exception as exc:
        logger.warning("Could not reach Ollama at startup: %s", exc)

# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    prompt: str = Field(..., description="User image generation request")
    quality: Optional[str] = Field("balanced", description="fast | balanced | high")
    reference_image_base64: Optional[str] = Field(None, description="Base64 reference image")
    session_id: Optional[str] = Field(None, description="Session identifier")


class GenerateResponse(BaseModel):
    image_base64: Optional[str]
    route_result: dict
    review: Optional[dict]
    retry_used: bool
    critic_result: Optional[dict]
    session_id: str
    generation_time_ms: float


class RouteRequest(BaseModel):
    prompt: str


class AnalyzeRequest(BaseModel):
    image_base64: str
    question: Optional[str] = "Describe this image in detail."


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class PullModelsRequest(BaseModel):
    models: List[str]

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health_check():
    """Simple health check endpoint."""
    return {"status": "ok", "service": "mini-assistant-image-system"}


@app.post("/api/image/route")
async def route_only(req: RouteRequest):
    """
    Classify a prompt and return the routing decision without generating an image.
    Useful for debugging the router.
    """
    try:
        route_result = await _get_router().route(req.prompt)
        return {"route_result": route_result}
    except Exception as exc:
        logger.error("Route endpoint error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/image/generate", response_model=GenerateResponse)
async def generate_image(req: GenerateRequest):
    """
    Full image generation pipeline:
    1. RouterBrain classifies the request.
    2. If not an image intent, delegate to the appropriate brain.
    3. PromptBuilder crafts positive + negative prompts.
    4. ComfyUIClient generates the image.
    5. ImageReviewer scores the result (unless quality=='fast').
    6. CriticBrain evaluates; retries once if warranted.
    7. EmbedBrain stores successful routes for memory.
    """
    session_id = req.session_id or str(uuid.uuid4())
    start_time = time.perf_counter()

    # ---- Step 1: Route ----
    reference_bytes = None
    if req.reference_image_base64:
        try:
            reference_bytes = base64.b64decode(req.reference_image_base64)
        except Exception:
            logger.warning("Could not decode reference_image_base64")

    try:
        route_result = await _get_router().route(req.prompt, reference_image=reference_bytes)
    except Exception as exc:
        logger.error("Routing failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Routing error: {exc}")

    intent = route_result.get("intent", "chat")

    # ---- Step 2: Non-image intents ----
    if intent in ("chat", "planning"):
        ollama = _get_ollama()
        try:
            from ..services.ollama_client import _model_name
            reply = await ollama.run_prompt(
                model=_model_name("router"),
                prompt=req.prompt,
                temperature=0.7,
            )
        except Exception as exc:
            reply = f"I'm having trouble responding right now: {exc}"

        elapsed = (time.perf_counter() - start_time) * 1000
        return GenerateResponse(
            image_base64=None,
            route_result=route_result,
            review=None,
            retry_used=False,
            critic_result=None,
            session_id=session_id,
            generation_time_ms=round(elapsed, 1),
        )

    if intent == "coding":
        coding = _get_coding()
        try:
            reply = await coding.run(req.prompt)
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
        )

    # ---- Step 3: Image generation ----
    checkpoint_key = route_result.get("selected_checkpoint", "anime_general")
    quality = req.quality or "balanced"

    # Load model registry to get checkpoint filename
    try:
        import json as _json
        from pathlib import Path
        registry_path = Path(__file__).parent.parent / "config" / "model_registry.json"
        with open(registry_path) as f:
            registry = _json.load(f)
        checkpoint_info = registry["image_checkpoints"].get(checkpoint_key, {})
        checkpoint_file = checkpoint_info.get("file", f"{checkpoint_key}.safetensors")
        checkpoint_type = checkpoint_info.get("type", "SD1.5")
    except Exception:
        checkpoint_file = f"{checkpoint_key}.safetensors"
        checkpoint_type = "SD1.5"

    # Build prompts
    try:
        pb = _get_prompt_builder()
        prompts = await pb.build(req.prompt, route_result)
        positive_prompt = prompts["positive"]
        negative_prompt = prompts["negative"]
        width, height = pb.size_for_visual_mode(
            route_result.get("visual_mode", "portrait"), checkpoint_type, quality
        )
        steps = pb.steps_for_quality(quality, checkpoint_type)
        cfg = pb.cfg_for_style(route_result.get("style_family", "anime"))
    except Exception as exc:
        logger.error("PromptBuilder failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Prompt build error: {exc}")

    # Generate image via ComfyUI
    comfyui = _get_comfyui()
    workflow = comfyui.build_standard_workflow(
        checkpoint=checkpoint_file,
        positive_prompt=positive_prompt,
        negative_prompt=negative_prompt,
        width=width,
        height=height,
        steps=steps,
        cfg=cfg,
    )

    image_bytes: Optional[bytes] = None
    review: Optional[dict] = None
    critic_result: Optional[dict] = None
    retry_used = False

    try:
        images = await comfyui.generate(workflow, timeout=300)
        image_bytes = images[0] if images else None
    except Exception as exc:
        logger.error("ComfyUI generation failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail=f"ComfyUI error: {exc}")

    # ---- Step 4: Review (skip for fast quality) ----
    if image_bytes and quality != "fast":
        try:
            from ..services.image_reviewer import ImageReviewer
            reviewer = ImageReviewer()
            review = await reviewer.review_image(image_bytes, req.prompt, route_result)
        except Exception as exc:
            logger.warning("Image review failed: %s", exc)
            review = None

    # ---- Step 5: Critic evaluation + single retry ----
    if review and image_bytes:
        try:
            critic = _get_critic()
            critic_result = await critic.evaluate(req.prompt, route_result, review)

            if critic_result.get("should_retry"):
                adjusted = critic_result.get("adjusted_params", {})
                alt_checkpoint_key = critic_result.get("alt_checkpoint") or checkpoint_key
                try:
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

    # ---- Step 6: Store successful route ----
    quality_score = review.get("quality_score", 0.7) if review else 0.7
    if image_bytes and quality_score >= 0.5:
        try:
            await _get_embed().store_successful_route(req.prompt, route_result, quality_score)
        except Exception as exc:
            logger.warning("EmbedBrain store failed: %s", exc)

    elapsed = (time.perf_counter() - start_time) * 1000

    image_b64 = base64.b64encode(image_bytes).decode("utf-8") if image_bytes else None

    return GenerateResponse(
        image_base64=image_b64,
        route_result=route_result,
        review=review,
        retry_used=retry_used,
        critic_result=critic_result,
        session_id=session_id,
        generation_time_ms=round(elapsed, 1),
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
    Multi-purpose chat endpoint.

    Automatically detects if the message requires image generation and
    delegates accordingly. For pure chat, uses the router model.
    """
    session_id = req.session_id or str(uuid.uuid4())

    # Route to detect intent
    try:
        route_result = await _get_router().route(req.message)
    except Exception as exc:
        logger.error("Chat routing failed: %s", exc)
        route_result = {"intent": "chat"}

    intent = route_result.get("intent", "chat")

    if intent in ("image_generation", "image_edit"):
        # Delegate to the full generation pipeline by reusing the endpoint logic
        gen_req = GenerateRequest(prompt=req.message, session_id=session_id)
        return await generate_image(gen_req)

    if intent == "coding":
        try:
            reply = await _get_coding().run(req.message)
        except Exception as exc:
            reply = f"Coding brain error: {exc}"
    else:
        # General chat via router model
        try:
            ollama = _get_ollama()
            from ..services.ollama_client import _model_name
            reply = await ollama.run_prompt(
                model=_model_name("router"),
                prompt=req.message,
                temperature=0.7,
            )
        except Exception as exc:
            reply = f"I'm having trouble responding right now: {exc}"

    return {
        "reply": reply,
        "intent": intent,
        "route_result": route_result,
        "session_id": session_id,
    }


@app.get("/api/models/status")
async def models_status():
    """Check which Ollama models are available locally."""
    ollama = _get_ollama()
    try:
        available = await ollama.list_models()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Ollama unreachable: {exc}")

    import json as _json
    from pathlib import Path
    registry_path = Path(__file__).parent.parent / "config" / "model_registry.json"
    try:
        with open(registry_path) as f:
            registry = _json.load(f)
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
