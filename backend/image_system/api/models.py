"""
Pydantic request and response models for the image system API.

All endpoints use these models for consistent validation and serialisation.
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    prompt: str = Field(..., description="User image generation request")
    quality: str = Field("balanced", description="fast | balanced | high")
    session_id: Optional[str] = Field(None, description="Session identifier for tracking")
    request_id: Optional[str] = Field(None, description="Client-generated UUID for deduplication")
    reference_image_base64: Optional[str] = Field(None, description="Base64-encoded reference image")

    # dry_run: return routing plan without actually generating
    dry_run: bool = Field(False, description="If true, return the plan without generating an image")

    # Manual overrides — any field set here bypasses the router decision
    override_checkpoint: Optional[str] = Field(None, description="Force a specific checkpoint key")
    override_workflow: Optional[str] = Field(None, description="Force a specific workflow key")
    override_width: Optional[int] = Field(None, ge=64, le=2048, description="Force output width")
    override_height: Optional[int] = Field(None, ge=64, le=2048, description="Force output height")
    override_steps: Optional[int] = Field(None, ge=1, le=150, description="Force sampler steps")
    override_cfg: Optional[float] = Field(None, ge=1.0, le=30.0, description="Force CFG scale")
    override_seed: Optional[int] = Field(None, ge=0, description="Force random seed")

    # img2img / inpaint / reference (Phase 7 — ComfyUI smart router)
    init_image_base64: Optional[str] = Field(None, description="Base64 init image for img2img")
    denoise_strength: Optional[float] = Field(None, ge=0.0, le=1.0)
    mask_image_base64: Optional[str] = Field(None, description="Base64 mask for inpainting/edit mode")
    pose_image_base64: Optional[str] = Field(None, description="Base64 pose guide image → reference-guided mode")
    style_image_base64: Optional[str] = Field(None, description="Base64 style reference image → reference-guided mode")
    controlnet_image_base64: Optional[str] = Field(None, description="Base64 ControlNet guide image")
    controlnet_name: Optional[str] = Field(None, description="ControlNet model filename")
    controlnet_strength: Optional[float] = Field(None, ge=0.0, le=2.0)


class RouteRequest(BaseModel):
    prompt: str


class AnalyzeRequest(BaseModel):
    image_base64: str
    question: Optional[str] = "Describe this image in detail."


class ChatHistoryMessage(BaseModel):
    role: str   # "user" | "assistant"
    content: str

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    history: Optional[List[ChatHistoryMessage]] = []  # recent conversation turns
    image_base64: Optional[str] = None               # single attached image (legacy)
    images_base64: Optional[List[str]] = None        # multiple attached images (Phase 5+)
    preferred_model: Optional[str] = None            # Ollama model override (Phase 6)
    vibe_mode: bool = False                          # Vibe Code mode: skip Q&A, build immediately
    chat_mode: Optional[str] = None                  # explicit mode: 'image' | 'build' | None (auto)
    request_id: Optional[str] = None                 # client-generated UUID for deduplication
    timezone: Optional[str] = None                   # IANA timezone (e.g. "America/New_York")


class AutoFixRequest(BaseModel):
    html: str                                        # current full app HTML
    errors: Optional[List[str]] = []                # JS errors captured from iframe
    dom_report: Optional[str] = None                # DOM inspector snapshot (buttons, state, hidden els)
    iteration: int = 1                              # which pass (1-5)
    session_id: Optional[str] = None


class PullModelsRequest(BaseModel):
    models: List[str]


class SummarizeRequest(BaseModel):
    messages: List[ChatHistoryMessage]


class ShareRequest(BaseModel):
    html: str                       # full app HTML to share
    thumbnail_base64: Optional[str] = None  # JPEG thumbnail captured from the app preview


class CommunityRequest(BaseModel):
    share_id: str          # id from /api/share
    title: str = "Community App"
    author_name: str = "Anonymous"


class VisualReviewRequest(BaseModel):
    html: str                        # current full app HTML
    screenshot_base64: str           # JPEG screenshot of the rendered iframe
    session_id: Optional[str] = None


class OrchestrationRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    mode: str = "chat"               # "chat" | "builder" | "image"
    history: Optional[List[ChatHistoryMessage]] = []
    has_existing_code: bool = False
    vibe_mode: bool = False


class CreationExportRequest(BaseModel):
    project_id:    str
    project_title: str = "Untitled Project"
    created_at:    str = ""
    history:       Optional[List[ChatHistoryMessage]] = []
    creator_name:  Optional[str] = None
    description:   Optional[str] = None
    notes:         Optional[str] = None
    export_format: str = "json"      # "json" | "txt"


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class RouteResult(BaseModel):
    intent: str
    style_family: Optional[str]
    anime_genre: Optional[str]
    visual_mode: str
    selected_checkpoint: Optional[str]
    selected_workflow: Optional[str]
    confidence: float
    anime_score: float
    realism_score: float
    fantasy_score: float
    needs_reference_analysis: bool = False
    needs_upscale: bool = False
    needs_face_detail: bool = False
    # Warning fields injected by routing_guard
    low_conf_warning: Optional[str] = Field(None, alias="_low_confidence_warning")
    compat_warning: Optional[str] = Field(None, alias="_compatibility_warning")

    class Config:
        populate_by_name = True


class GenerationPlan(BaseModel):
    """Returned in dry_run mode — shows exactly what would be generated."""
    checkpoint: str
    checkpoint_file: str
    workflow: str
    positive_prompt: str
    negative_prompt: str
    width: int
    height: int
    steps: int
    cfg: float
    seed: Optional[int]
    quality: str
    overrides_applied: Dict[str, Any] = {}


class DryRunResponse(BaseModel):
    dry_run: bool = True
    session_id: str
    route_result: Dict[str, Any]
    plan: GenerationPlan
    prompt_warnings: List[str] = []


class ReviewResult(BaseModel):
    quality_score: float
    style_match: str
    retry_recommended: bool
    anatomy_score: float = 0.7
    composition_score: float = 0.7
    issues: List[str] = []
    retry_reason: Optional[str] = None
    alt_checkpoint: Optional[str] = None


class GenerateResponse(BaseModel):
    image_base64: Optional[str]
    route_result: Dict[str, Any]
    review: Optional[Dict[str, Any]]
    retry_used: bool
    critic_result: Optional[Dict[str, Any]]
    session_id: str
    generation_time_ms: float
    prompt_warnings: List[str] = []
    dry_run: bool = False
    plan: Optional[GenerationPlan] = None


class ModelStatusResponse(BaseModel):
    available_models: List[str]
    required_status: Dict[str, Any]


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    code: int
