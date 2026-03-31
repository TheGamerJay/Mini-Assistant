"""
Ad Mode Router — isolated AI-powered ad creation add-on.

All routes are isolated under /api/ad-mode/ and /api/checkout/ad-mode.
This module does NOT touch main plan logic, credits, or billing.

MongoDB collections used:
  ad_mode_profiles         — business profiles (one per user)
  ad_mode_campaigns        — campaigns
  ad_mode_ad_sets          — generated ad sets (creatives)
  ad_mode_generation_logs  — generation audit log

Routes:
  GET  /api/ad-mode/status
  POST /api/checkout/ad-mode
  POST /api/ad-mode/profile/generate
  GET  /api/ad-mode/profile
  PUT  /api/ad-mode/profile
  POST /api/ad-mode/campaigns
  GET  /api/ad-mode/campaigns
  GET  /api/ad-mode/campaigns/{campaign_id}
  POST /api/ad-mode/generate
  POST /api/ad-mode/regenerate-copy
  POST /api/ad-mode/regenerate-image
  GET  /api/ad-mode/assets/{ad_set_id}/download
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import stripe
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Router setup
# ---------------------------------------------------------------------------

ad_mode_router = APIRouter(tags=["ad-mode"])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CLAUDE_MODEL       = "claude-sonnet-4-6"
DALLE_IMAGE_MODEL  = os.environ.get("OPENAI_IMAGE_MODEL", "dall-e-3")
DALLE_IMAGE_SIZE   = "1024x1024"
FRONTEND_URL       = os.environ.get("FRONTEND_URL", "http://localhost:3000")
JWT_SECRET         = os.environ.get("JWT_SECRET", "mini_assistant_jwt_secret_2025")
JWT_ALGORITHM      = "HS256"

# ---------------------------------------------------------------------------
# Auth helpers (mirrors stripe_handler pattern)
# ---------------------------------------------------------------------------


def _decode_bearer(authorization: str | None) -> dict | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        return None
    try:
        from jose import jwt  # noqa: PLC0415
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        uid = payload.get("sub")
        if not uid or not isinstance(uid, str):
            return None
        return payload
    except Exception:
        return None


async def _require_user(authorization: str | None) -> dict:
    """Decode JWT, return user doc, or raise 401."""
    payload = _decode_bearer(authorization)
    if not payload:
        raise HTTPException(401, "Authentication required")
    db = await _get_db()
    user = await db["users"].find_one({"id": payload["sub"]})
    if not user:
        raise HTTPException(401, "User not found")
    return user


async def _require_ad_mode(authorization: str | None) -> dict:
    """Like _require_user but also enforces has_ad_mode == True."""
    user = await _require_user(authorization)
    if not user.get("has_ad_mode", False):
        raise HTTPException(403, "Ad Mode subscription required")
    return user


async def _get_db():
    try:
        import server as _srv  # noqa: PLC0415
        return _srv.db
    except Exception as exc:
        raise HTTPException(503, "Database unavailable") from exc


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class AdModeCheckoutRequest(BaseModel):
    billing_period: str = "monthly"   # "monthly" | "yearly"


class BusinessProfileInput(BaseModel):
    business_name:   str
    product_name:    str
    description:     str
    audience:        str
    goal:            str   # sales | traffic | leads | awareness
    tone:            str   # professional | casual | bold | playful | urgent
    website_url:     Optional[str] = None


class UpdateProfileRequest(BaseModel):
    business_name:        Optional[str] = None
    product_name:         Optional[str] = None
    description:          Optional[str] = None
    audience:             Optional[str] = None
    goal:                 Optional[str] = None
    tone:                 Optional[str] = None
    website_url:          Optional[str] = None
    generated_profile:    Optional[Dict[str, Any]] = None


class CreateCampaignRequest(BaseModel):
    name:                str
    business_profile_id: str
    goal:                str
    audience:            Optional[str] = None
    tone:                Optional[str] = None
    image_style:         Optional[str] = None
    image_format:        Optional[str] = None
    visual_consistency:  bool = True
    people_in_image:     Optional[str] = None
    copy_angle:          Optional[str] = None


class GenerateAdsRequest(BaseModel):
    campaign_id:          str
    business_profile_id:  str
    goal:                 Optional[str] = None
    audience:             Optional[str] = None
    tone:                 Optional[str] = None
    num_concepts:         int = 3
    image_style:          Optional[str] = None
    image_format:         Optional[str] = None
    visual_consistency:   bool = True
    people_in_image:      Optional[str] = None
    copy_angle:           Optional[str] = None


class RegenerateCopyRequest(BaseModel):
    ad_set_id:   str
    campaign_id: str


class RegenerateImageRequest(BaseModel):
    ad_set_id:    str
    image_prompt: str


# ---------------------------------------------------------------------------
# AI helpers — Claude
# ---------------------------------------------------------------------------


async def _claude_complete(prompt: str, system: str = "") -> str:
    """Call Claude and return the text reply."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise HTTPException(503, "Claude API not configured (ANTHROPIC_API_KEY)")
    try:
        import anthropic as _am  # noqa: PLC0415
        client = _am.AsyncAnthropic(api_key=api_key)
        msgs: list = [{"role": "user", "content": prompt}]
        resp = await client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2048,
            system=system or "You are an expert marketing copywriter and brand strategist.",
            messages=msgs,
        )
        return resp.content[0].text.strip()
    except Exception as exc:
        log.error("Claude API error: %s", exc)
        raise HTTPException(502, f"Claude API error: {exc}") from exc


# ---------------------------------------------------------------------------
# AI helpers — DALL-E
# ---------------------------------------------------------------------------


async def _dalle_generate(prompt: str) -> str:
    """Generate image with DALL-E, return base64 string."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise HTTPException(503, "OpenAI API not configured (OPENAI_API_KEY)")
    try:
        import openai as _oai  # noqa: PLC0415
        client = _oai.AsyncOpenAI(api_key=api_key)
        resp = await client.images.generate(
            model=DALLE_IMAGE_MODEL,
            prompt=prompt,
            n=1,
            size=DALLE_IMAGE_SIZE,
            response_format="b64_json",
        )
        return resp.data[0].b64_json
    except Exception as exc:
        log.error("DALL-E API error: %s", exc)
        raise HTTPException(502, f"DALL-E API error: {exc}") from exc


# ---------------------------------------------------------------------------
# Business profile generation
# ---------------------------------------------------------------------------

_PROFILE_SYSTEM = """You are an expert brand strategist and marketing consultant.
Generate a structured business/brand profile in JSON format only.
No explanation, no markdown code fences — just the raw JSON object."""

_PROFILE_PROMPT_TEMPLATE = """
Generate a comprehensive brand profile for this business:

Business Name: {business_name}
Product/Service: {product_name}
Description: {description}
Target Audience: {audience}
Primary Goal: {goal}
Tone/Style: {tone}
Website: {website_url}

Return a JSON object with these exact keys:
{{
  "core_identity": "2-3 sentence brand essence statement",
  "positioning": "How this brand is positioned vs competitors",
  "key_selling_points": ["point 1", "point 2", "point 3", "point 4"],
  "audience_summary": "Detailed audience psychographic and demographic summary",
  "competitive_angle": "What makes this brand distinctly better/different",
  "recommended_ad_directions": [
    {{"angle": "benefit-driven", "rationale": "..."}},
    {{"angle": "emotional", "rationale": "..."}},
    {{"angle": "problem-solution", "rationale": "..."}},
    {{"angle": "curiosity", "rationale": "..."}},
    {{"angle": "direct-cta", "rationale": "..."}}
  ],
  "brand_voice_guidelines": "2-3 sentences on how copy should sound/feel"
}}
"""


async def _generate_business_profile(info: BusinessProfileInput) -> Dict[str, Any]:
    prompt = _PROFILE_PROMPT_TEMPLATE.format(
        business_name=info.business_name,
        product_name=info.product_name,
        description=info.description,
        audience=info.audience,
        goal=info.goal,
        tone=info.tone,
        website_url=info.website_url or "Not provided",
    )
    raw = await _claude_complete(prompt, system=_PROFILE_SYSTEM)
    # Strip any accidental markdown fences
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0]
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        # Return as plain text if JSON parse fails
        return {"raw_profile": raw}


# ---------------------------------------------------------------------------
# Ad set generation
# ---------------------------------------------------------------------------

# Image style → DALL-E style prefix lookup
_IMAGE_STYLE_PREFIXES: dict[str, str] = {
    "Product UI / SaaS Dashboard":
        "Professional SaaS product UI screenshot mockup on a dark background, glowing interface panels, "
        "clean dashboard with charts and metrics, premium dark theme, subtle blue/cyan accent glow",
    "Solo Founder Workspace":
        "Moody solo founder workspace, laptop open with code or dashboard, late-night productivity aesthetic, "
        "soft desk lamp lighting, dark background, focus and hustle vibe",
    "Futuristic AI Interface":
        "Futuristic AI holographic interface, glowing data streams, neural network visualization, "
        "deep navy/black background, blue and purple light trails, ultra-modern tech aesthetic",
    "Dark Tech":
        "Dark tech product photography, deep black background, blue/cyan neon accent lighting, "
        "dramatic shadows, premium hardware or software visualization, sleek and minimal",
    "Clean Corporate":
        "Clean modern corporate aesthetic, white and light grey tones, minimal layout, "
        "professional business setting, soft shadows, polished and trustworthy",
    "Startup Team":
        "Dynamic startup team environment, collaborative workspace, diverse young professionals, "
        "bright modern office, energy and momentum, natural lighting",
    "Minimal Modern":
        "Ultra-minimal modern composition, generous white space, single hero element, "
        "clean geometry, muted accent color, sophisticated and editorial",
    "Cinematic":
        "Cinematic wide-angle shot, dramatic lighting, rich color grading, "
        "film-quality composition, deep shadows and bright highlights, storytelling mood",
    "Illustration":
        "Clean vector illustration style, flat design with subtle depth, "
        "limited modern color palette, bold shapes, professional and friendly",
    "3D Render":
        "High-quality 3D render, photorealistic materials, studio lighting, "
        "floating UI elements or product, dark background, glossy surfaces, premium feel",
    "No Image": "",
}

_IMAGE_FORMAT_SUFFIXES: dict[str, str] = {
    "photorealistic": "photorealistic, DSLR quality, sharp focus, professional photography",
    "illustration":   "digital illustration, clean vector art, bold flat design",
    "3D":             "3D render, CGI quality, ray-traced lighting, octane render",
    "UI mockup":      "UI/UX product mockup, device frame, app interface preview, clean layout",
}

# Styles to prefer for SaaS/AI/automation/developer products
_SAAS_KEYWORDS = {
    "saas", "ai", "artificial intelligence", "automation", "workflow",
    "developer tool", "developer", "app builder", "assistant", "software",
    "platform", "dashboard", "api", "code", "coding", "startup", "tool",
    "productivity", "no-code", "low-code", "integration", "bot", "agent",
}
_SAAS_DEFAULT_STYLE = "Dark Tech"

_STYLE_AVOIDS: dict[str, str] = {
    "Dark Tech":
        "Avoid: warm lifestyle office scenes, smiling corporate groups, bright airy stock photography, "
        "generic business handshakes, sunny outdoor settings.",
    "Product UI / SaaS Dashboard":
        "Avoid: abstract art, portrait photography, cinematic lifestyle shots, nature scenes, "
        "hand-drawn sketches, people without context.",
    "Solo Founder Workspace":
        "Avoid: multiple people, conference rooms, group collaboration, open-plan office crowds, "
        "formal business attire, staged corporate poses.",
    "Futuristic AI Interface":
        "Avoid: real-world photography, natural lighting, vintage aesthetics, warm colour palettes, "
        "traditional office environments.",
    "Clean Corporate":
        "Avoid: neon cyberpunk lighting, sci-fi UI overload, dark moody aesthetics, heavy grain, "
        "cluttered compositions, aggressive colour contrasts.",
    "Startup Team":
        "Avoid: formal corporate settings, grey cubicle offices, solitary scenes with no energy, "
        "dark moody cyberpunk lighting.",
    "Minimal Modern":
        "Avoid: busy compositions, multiple focal points, heavy textures, dark backgrounds, "
        "neon lighting, photorealistic people.",
    "Cinematic":
        "Avoid: flat lighting, bland stock photography, white backgrounds, generic corporate imagery, "
        "cartoon or illustration styles.",
    "Illustration":
        "Avoid: photorealistic rendering, dark moody photography, complex 3D scenes, "
        "heavy texture overlays, cinematic film grain.",
    "3D Render":
        "Avoid: flat 2D illustration, photographic backgrounds, hand-drawn elements, "
        "amateur renders with visible aliasing.",
}

_PEOPLE_RULES: dict[str, str] = {
    "yes":      "Include one or two professional people naturally interacting with the product.",
    "no":       "No people in the image — focus entirely on the product, interface, or abstract concept.",
    "optional": "Only include people if it naturally improves the composition.",
}


def _detect_saas_product(profile: dict) -> bool:
    """Return True if the brand profile looks like a SaaS/AI/developer product."""
    text = " ".join([
        str(profile.get("core_identity", "")),
        str(profile.get("positioning", "")),
        str(profile.get("brand_voice_guidelines", "")),
        str(profile.get("competitive_angle", "")),
    ]).lower()
    return any(kw in text for kw in _SAAS_KEYWORDS)


def _build_image_prompt(
    concept_prompt: str,
    image_style: str | None,
    image_format: str | None,
    people_in_image: str | None,
    consistency_anchor: str | None,
) -> str:
    """Combine concept-specific prompt with style controls into a final DALL-E prompt."""
    style   = image_style   or "Dark Tech"
    fmt     = image_format  or "photorealistic"
    people  = people_in_image or "no"

    if style == "No Image":
        return ""

    style_prefix  = _IMAGE_STYLE_PREFIXES.get(style, _IMAGE_STYLE_PREFIXES["Dark Tech"])
    format_suffix = _IMAGE_FORMAT_SUFFIXES.get(fmt, _IMAGE_FORMAT_SUFFIXES["photorealistic"])
    people_rule   = _PEOPLE_RULES.get(people, _PEOPLE_RULES["no"])
    avoid_rule    = _STYLE_AVOIDS.get(style, "")
    anchor        = f"Maintain consistent visual style: {consistency_anchor}. " if consistency_anchor else ""

    parts = [
        style_prefix,
        concept_prompt,
        people_rule,
        format_suffix,
        anchor,
        "No text, logos, or watermarks in the image. No stock photo clichés. High quality, ad-ready.",
        avoid_rule,
    ]
    return " ".join(p for p in parts if p).strip()


_COPY_ANGLE_INSTRUCTIONS: dict[str, str] = {
    "Direct Response":
        "Write hard-hitting, conversion-focused copy. Lead with the strongest benefit. "
        "Use imperative CTAs. Every sentence must earn its place. Cut all fluff.",
    "Curiosity":
        "Open with an intriguing question or surprising insight. Build tension and withhold "
        "the full answer until the CTA. Make the reader feel they must click to understand.",
    "Problem-Solution":
        "Start by naming a specific pain the audience feels daily. Amplify it briefly, "
        "then position the product as the clear, obvious solution. Close with relief.",
    "Founder Story":
        "Write in first-person founder voice. Share a brief authentic moment of struggle "
        "or insight that led to building this. Make it personal, vulnerable, and relatable.",
    "Feature-Driven":
        "Lead with the most impressive, concrete feature or capability. Describe what it "
        "does in plain language. Stack 2-3 supporting features. End with a capability-focused CTA.",
}

_AD_COPY_SYSTEM = """You are an expert direct-response copywriter specialising in high-converting digital ads.

RULES — follow these strictly:
- NEVER invent statistics, user counts, testimonials, revenue figures, percentages, rankings (#1), guarantees, or performance claims unless the brand profile explicitly provides them.
- Write bold, confident copy that is believable — no hype, no "10x your revenue overnight" nonsense.
- Focus on real, concrete benefits: speed, automation, replacing multiple tools, helping solo founders scale.
- Keep hooks punchy and curiosity-driven. Keep headlines clear and specific.
- Write captions that educate and persuade in 40-80 words — no fluff.
- CTAs must be action-oriented and specific (e.g. "Start free today", "See it in action", "Build your first app").

Return valid JSON only — no markdown, no explanation."""

_AD_COPY_PROMPT = """
Using this brand profile and campaign brief, generate {num_concepts} distinct ad concepts.

BRAND PROFILE:
{profile_json}

CAMPAIGN:
- Goal: {goal}
- Audience: {audience}
- Tone: {tone}
- Image Style: {image_style}
- Copy Angle Direction: {copy_angle_instruction}

{angle_constraint}

Return a JSON array. Each object must have exactly these keys:
{{
  "concept_number": 1,
  "angle": "benefit-driven",
  "hook": "Attention-grabbing opening line. Max 12 words. Bold but believable.",
  "headline": "Main ad headline. Max 8 words. Clear and specific.",
  "caption": "Ad body copy. 40-80 words. Persuasive, no invented claims, on-brand voice.",
  "cta": "Call to action. Max 5 words. Action-oriented.",
  "image_prompt": "Describe the core visual concept in 1-2 sentences: what is shown, the mood, key elements. Style and format will be applied separately — just describe what the image should depict."
}}
"""

# Claim patterns that indicate invented data — used in safety validation
_CLAIM_PATTERNS = [
    r"\b\d+[,.]?\d*\s*%",                          # percentages
    r"\b(#\s*1|number\s*one)\b",                   # #1 ranking
    r"\b\d+[kKmMbB]\+?\s*(users?|customers?|clients?|businesses?|companies?)\b",
    r"\b(guaranteed?|guarantee)\b",
    r"\b\d+x\s*(faster|better|more|growth|revenue|roi)\b",
    r"\bjoin\s+\d+",                               # "join 50,000 users"
    r"\b\d{4,}[\s,]?\d*\s*(users?|people|businesses?|customers?)\b",
    r"\brated\s+\d+(\.\d+)?\s*/\s*5\b",           # "rated 4.9/5"
    r"\b(as\s+seen\s+in|featured\s+in)\b",
]


_SAFE_CLAIM_REWRITES = """
The following concepts contain invented claims (statistics, user counts, percentages, guarantees, or rankings not provided in the brand profile).
Rewrite ONLY the flagged concepts to remove all invented claims while keeping the same angle and energy.
Return a JSON array with the same structure — only the rewritten concepts, in the same order.
Flagged concepts:
{flagged_json}
"""

import re as _re  # noqa: PLC0415 (module level is fine here, but keeping lazy import pattern)


def _has_invented_claims(text: str) -> bool:
    """Return True if text contains patterns that look like invented claims."""
    for pattern in _CLAIM_PATTERNS:
        if _re.search(pattern, text, _re.IGNORECASE):
            return True
    return False


async def _validate_and_clean_concepts(concepts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Check each concept for invented claims; rewrite flagged ones via Claude."""
    flagged = []
    clean   = []
    for c in concepts:
        combined = " ".join([
            c.get("hook", ""), c.get("headline", ""),
            c.get("caption", ""), c.get("cta", ""),
        ])
        if _has_invented_claims(combined):
            flagged.append(c)
            log.warning("Concept %s flagged for invented claims: %s", c.get("concept_number"), combined[:120])
        else:
            clean.append(c)

    if not flagged:
        return concepts

    # Rewrite flagged concepts
    try:
        rewrite_prompt = _SAFE_CLAIM_REWRITES.format(flagged_json=json.dumps(flagged, indent=2))
        raw = await _claude_complete(rewrite_prompt, system=_AD_COPY_SYSTEM)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.rsplit("```", 1)[0]
        rewritten = json.loads(raw.strip())
        if not isinstance(rewritten, list):
            rewritten = [rewritten]
        # Merge: replace flagged with rewritten in original order
        rewritten_by_num = {r.get("concept_number"): r for r in rewritten}
        result = []
        for c in concepts:
            num = c.get("concept_number")
            result.append(rewritten_by_num.get(num, c))
        log.info("Rewrote %d concepts to remove invented claims", len(flagged))
        return result
    except Exception as exc:
        log.warning("Claim rewrite failed (%s) — returning originals", exc)
        return concepts


async def _generate_ad_concepts(
    profile: Dict[str, Any],
    goal: str,
    audience: str,
    tone: str,
    num_concepts: int,
    image_style: str | None = None,
    copy_angle: str | None = None,
) -> List[Dict[str, Any]]:
    angle_instruction = _COPY_ANGLE_INSTRUCTIONS.get(copy_angle or "", "")
    angle_constraint  = (
        f"All {num_concepts} concepts MUST follow the '{copy_angle}' angle direction above."
        if copy_angle else
        f"Each concept MUST use a different angle from: benefit-driven, emotional, "
        f"problem-solution, curiosity, direct-cta, urgency, value-stack"
    )
    prompt = _AD_COPY_PROMPT.format(
        profile_json=json.dumps(profile, indent=2),
        goal=goal,
        audience=audience,
        tone=tone,
        num_concepts=num_concepts,
        image_style=image_style or "Dark Tech",
        copy_angle_instruction=angle_instruction or "Use the best angle for the campaign goal.",
        angle_constraint=angle_constraint,
    )
    raw = await _claude_complete(prompt, system=_AD_COPY_SYSTEM)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0]
    try:
        concepts = json.loads(raw.strip())
        if not isinstance(concepts, list):
            concepts = [concepts]
        # Safety: validate and clean invented claims
        concepts = await _validate_and_clean_concepts(concepts)
        return concepts
    except json.JSONDecodeError:
        log.warning("Ad copy JSON parse failed, returning raw text")
        return [{"raw": raw, "angle": "unknown"}]


# ---------------------------------------------------------------------------
# Stripe checkout (Ad Mode add-on)
# ---------------------------------------------------------------------------


async def _get_or_create_stripe_customer(db, user: dict) -> str:
    existing = user.get("stripe_customer_id")
    if existing:
        return existing
    customer = stripe.Customer.create(
        email=user.get("email", ""),
        name=user.get("name", ""),
        metadata={"user_id": user.get("id", "")},
    )
    cid = customer["id"]
    await db["users"].update_one({"id": user["id"]}, {"$set": {"stripe_customer_id": cid}})
    return cid


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@ad_mode_router.get("/api/ad-mode/status")
async def ad_mode_status(authorization: str = Header(None)):
    """Return whether the authenticated user has Ad Mode access."""
    user = await _require_user(authorization)
    return {"has_ad_mode": bool(user.get("has_ad_mode", False))}


@ad_mode_router.post("/api/checkout/ad-mode")
async def checkout_ad_mode(
    body: AdModeCheckoutRequest,
    authorization: str = Header(None),
):
    """
    Create a Stripe Checkout session for the Ad Mode add-on.

    Uses STRIPE_AD_MODE_MONTHLY or STRIPE_AD_MODE_YEARLY based on billing_period.
    Reuses the user's existing Stripe customer.
    """
    if not stripe.api_key:
        raise HTTPException(503, "Stripe not configured")

    user = await _require_user(authorization)

    # Check if user already has Ad Mode
    if user.get("has_ad_mode", False):
        raise HTTPException(400, "You already have Ad Mode enabled. Manage it via billing portal.")

    # Resolve price ID
    if body.billing_period == "yearly":
        price_id = os.environ.get("STRIPE_AD_MODE_YEARLY", "")
    else:
        price_id = os.environ.get("STRIPE_AD_MODE_MONTHLY", "")

    if not price_id or not price_id.startswith("price_"):
        raise HTTPException(503, "Ad Mode pricing not configured. Contact support.")

    db = await _get_db()
    uid = user["id"]

    try:
        customer_id = await _get_or_create_stripe_customer(db, user)
        session = stripe.checkout.Session.create(
            customer=customer_id,
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            subscription_data={"metadata": {"user_id": uid}},
            success_url=f"{FRONTEND_URL}?checkout=success&session_id={{CHECKOUT_SESSION_ID}}&addon=ad_mode",
            cancel_url=f"{FRONTEND_URL}?checkout=cancelled&addon=ad_mode",
            metadata={
                "user_id":  uid,
                "price_id": price_id,
                "addon":    "ad_mode",
            },
            allow_promotion_codes=True,
        )
        return {"checkout_url": session.url, "session_id": session.id}
    except stripe.error.StripeError as exc:
        log.error("Ad Mode checkout Stripe error: %s", exc)
        raise HTTPException(502, f"Stripe error: {exc.user_message or str(exc)}") from exc


# ---------------------------------------------------------------------------
# Business Profile routes
# ---------------------------------------------------------------------------


@ad_mode_router.post("/api/ad-mode/profile/generate")
async def generate_profile(
    body: BusinessProfileInput,
    authorization: str = Header(None),
):
    """Generate a brand profile with Claude and save it."""
    user = await _require_ad_mode(authorization)
    user_id = user["id"]
    db = await _get_db()

    log.info("Generating brand profile for user=%s business=%s", user_id, body.business_name)
    generated = await _generate_business_profile(body)

    now = datetime.now(timezone.utc).isoformat()
    profile_id = str(uuid.uuid4())

    doc = {
        "id":                 profile_id,
        "user_id":            user_id,
        "business_name":      body.business_name,
        "product_name":       body.product_name,
        "description":        body.description,
        "audience":           body.audience,
        "goal":               body.goal,
        "tone":               body.tone,
        "website_url":        body.website_url,
        "generated_profile":  generated,
        "created_at":         now,
        "updated_at":         now,
    }

    # Upsert — one profile per user
    await db["ad_mode_profiles"].replace_one(
        {"user_id": user_id},
        doc,
        upsert=True,
    )

    # Log generation
    await db["ad_mode_generation_logs"].insert_one({
        "id":              str(uuid.uuid4()),
        "user_id":         user_id,
        "generation_type": "business_profile",
        "model_used":      CLAUDE_MODEL,
        "request_json":    body.model_dump(),
        "response_json":   generated,
        "created_at":      now,
    })

    return {"profile": doc}


@ad_mode_router.get("/api/ad-mode/profile")
async def get_profile(authorization: str = Header(None)):
    """Return the user's stored brand profile."""
    user = await _require_ad_mode(authorization)
    db = await _get_db()
    profile = await db["ad_mode_profiles"].find_one(
        {"user_id": user["id"]},
        {"_id": 0},
    )
    return {"profile": profile}  # None if not created yet — frontend shows setup form


@ad_mode_router.put("/api/ad-mode/profile")
async def update_profile(
    body: UpdateProfileRequest,
    authorization: str = Header(None),
):
    """Update the user's stored brand profile with partial edits."""
    user = await _require_ad_mode(authorization)
    db = await _get_db()

    existing = await db["ad_mode_profiles"].find_one({"user_id": user["id"]})
    if not existing:
        raise HTTPException(404, "No brand profile found. Generate one first.")

    updates: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
    patch = body.model_dump(exclude_none=True)
    updates.update(patch)

    await db["ad_mode_profiles"].update_one(
        {"user_id": user["id"]},
        {"$set": updates},
    )
    updated = await db["ad_mode_profiles"].find_one({"user_id": user["id"]}, {"_id": 0})
    return {"profile": updated}


# ---------------------------------------------------------------------------
# Campaign routes
# ---------------------------------------------------------------------------


@ad_mode_router.post("/api/ad-mode/campaigns")
async def create_campaign(
    body: CreateCampaignRequest,
    authorization: str = Header(None),
):
    """Create a new campaign under a brand profile."""
    user = await _require_ad_mode(authorization)
    db = await _get_db()

    # Verify profile belongs to user
    profile = await db["ad_mode_profiles"].find_one({
        "id": body.business_profile_id,
        "user_id": user["id"],
    })
    if not profile:
        raise HTTPException(404, "Brand profile not found")

    now = datetime.now(timezone.utc).isoformat()
    campaign = {
        "id":                  str(uuid.uuid4()),
        "user_id":             user["id"],
        "business_profile_id": body.business_profile_id,
        "name":                body.name,
        "goal":                body.goal,
        "audience":            body.audience or profile.get("audience", ""),
        "tone":                body.tone or profile.get("tone", ""),
        "image_style":         body.image_style or "Dark Tech",
        "image_format":        body.image_format or "photorealistic",
        "visual_consistency":  body.visual_consistency,
        "people_in_image":     body.people_in_image or "no",
        "copy_angle":          body.copy_angle,
        "status":              "active",
        "ad_set_count":        0,
        "created_at":          now,
        "updated_at":          now,
    }

    await db["ad_mode_campaigns"].insert_one({**campaign, "_id": campaign["id"]})
    campaign.pop("_id", None)
    return {"campaign": campaign}


@ad_mode_router.get("/api/ad-mode/campaigns")
async def list_campaigns(authorization: str = Header(None)):
    """List all campaigns for the user."""
    user = await _require_ad_mode(authorization)
    db = await _get_db()
    cursor = db["ad_mode_campaigns"].find(
        {"user_id": user["id"]},
        {"_id": 0},
        sort=[("created_at", -1)],
        limit=50,
    )
    campaigns = await cursor.to_list(50)
    return {"campaigns": campaigns}


@ad_mode_router.get("/api/ad-mode/campaigns/{campaign_id}")
async def get_campaign(
    campaign_id: str,
    authorization: str = Header(None),
):
    """Return a campaign with its ad sets."""
    user = await _require_ad_mode(authorization)
    db = await _get_db()

    campaign = await db["ad_mode_campaigns"].find_one(
        {"id": campaign_id, "user_id": user["id"]},
        {"_id": 0},
    )
    if not campaign:
        raise HTTPException(404, "Campaign not found")

    ad_sets_cursor = db["ad_mode_ad_sets"].find(
        {"campaign_id": campaign_id},
        {"_id": 0},
        sort=[("created_at", -1)],
    )
    ad_sets = await ad_sets_cursor.to_list(100)

    return {"campaign": campaign, "ad_sets": ad_sets}


# ---------------------------------------------------------------------------
# Ad generation routes
# ---------------------------------------------------------------------------


@ad_mode_router.post("/api/ad-mode/generate")
async def generate_ads(
    body: GenerateAdsRequest,
    authorization: str = Header(None),
):
    """
    Generate a full ad set: Claude copy + DALL-E images.

    For each of the num_concepts requested, Claude generates:
      hook, headline, caption, cta, image_prompt

    Then DALL-E generates an image per concept (parallel).
    """
    user = await _require_ad_mode(authorization)
    db = await _get_db()
    user_id = user["id"]

    # Verify campaign
    campaign = await db["ad_mode_campaigns"].find_one({
        "id": body.campaign_id,
        "user_id": user_id,
    })
    if not campaign:
        raise HTTPException(404, "Campaign not found")

    # Fetch brand profile
    profile_doc = await db["ad_mode_profiles"].find_one({
        "id": body.business_profile_id,
        "user_id": user_id,
    })
    if not profile_doc:
        raise HTTPException(404, "Brand profile not found")

    profile_data = profile_doc.get("generated_profile") or {}
    goal            = body.goal     or campaign.get("goal", "awareness")
    audience        = body.audience or campaign.get("audience", profile_doc.get("audience", "general"))
    tone            = body.tone     or campaign.get("tone",     profile_doc.get("tone", "professional"))
    num             = max(1, min(5, body.num_concepts))
    copy_angle      = body.copy_angle or campaign.get("copy_angle")

    # Smart image style default: SaaS/AI products get Dark Tech, others get what campaign stored
    _saas = _detect_saas_product(profile_data)
    _style_fallback = _SAAS_DEFAULT_STYLE if _saas else "Dark Tech"
    image_style  = body.image_style    or campaign.get("image_style",    _style_fallback)
    image_format = body.image_format   or campaign.get("image_format",   "photorealistic")
    people       = body.people_in_image or campaign.get("people_in_image", "no")
    consistency  = body.visual_consistency if body.visual_consistency is not None else campaign.get("visual_consistency", True)

    log.info("Generating %d ad concepts for user=%s campaign=%s style=%s angle=%s",
             num, user_id, body.campaign_id, image_style, copy_angle or "auto")

    # Persist visual settings back to campaign so they survive page reloads
    await db["ad_mode_campaigns"].update_one(
        {"id": body.campaign_id},
        {"$set": {
            "image_style":        image_style,
            "image_format":       image_format,
            "people_in_image":    people,
            "visual_consistency": consistency,
            "copy_angle":         copy_angle,
        }},
    )

    # Step 1: Generate copy with Claude (includes raw concept image_prompt)
    concepts = await _generate_ad_concepts(profile_data, goal, audience, tone, num, image_style, copy_angle)

    now = datetime.now(timezone.utc).isoformat()
    saved_sets: List[Dict[str, Any]] = []

    # Build a consistency anchor from the first concept so all images share the same vibe
    consistency_anchor: Optional[str] = None
    if consistency and concepts:
        first_prompt = concepts[0].get("image_prompt", "")
        consistency_anchor = (
            f"{image_style} aesthetic, {image_format} style, "
            f"{_IMAGE_STYLE_PREFIXES.get(image_style, '')[:80]}"
        ) if first_prompt else None

    # Step 2: For each concept, build full DALL-E prompt + generate image
    import asyncio as _asyncio  # noqa: PLC0415

    async def _gen_one(concept: Dict[str, Any]) -> Dict[str, Any]:
        raw_concept_prompt = concept.get("image_prompt", "")
        final_image_prompt = _build_image_prompt(
            raw_concept_prompt, image_style, image_format, people,
            consistency_anchor if consistency else None,
        )
        image_b64: Optional[str] = None
        if final_image_prompt:
            try:
                image_b64 = await _dalle_generate(final_image_prompt)
            except Exception as exc:
                log.warning("DALL-E failed for concept %s: %s", concept.get("concept_number"), exc)

        ad_set_id = str(uuid.uuid4())
        doc = {
            "id":                  ad_set_id,
            "campaign_id":         body.campaign_id,
            "business_profile_id": body.business_profile_id,
            "user_id":             user_id,
            "angle":               concept.get("angle", ""),
            "hook":                concept.get("hook", ""),
            "headline":            concept.get("headline", ""),
            "caption":             concept.get("caption", ""),
            "cta":                 concept.get("cta", ""),
            "image_prompt":        final_image_prompt,
            "image_base64":        image_b64,
            "metadata":            {
                "model_copy":         CLAUDE_MODEL,
                "model_image":        DALLE_IMAGE_MODEL if image_b64 else None,
                "goal":               goal,
                "audience":           audience,
                "tone":               tone,
                "image_style":        image_style,
                "image_format":       image_format,
                "people_in_image":    people,
                "visual_consistency": consistency,
            },
            "created_at":          now,
            "updated_at":          now,
        }
        await db["ad_mode_ad_sets"].insert_one({**doc, "_id": ad_set_id})
        doc.pop("_id", None)
        return doc

    # Generate all images in parallel (bounded concurrency)
    sem = _asyncio.Semaphore(3)

    async def _bounded(concept: Dict[str, Any]) -> Dict[str, Any]:
        async with sem:
            return await _gen_one(concept)

    saved_sets = list(await _asyncio.gather(*[_bounded(c) for c in concepts]))

    # Update campaign ad_set_count
    await db["ad_mode_campaigns"].update_one(
        {"id": body.campaign_id},
        {
            "$inc": {"ad_set_count": len(saved_sets)},
            "$set": {"updated_at": now},
        },
    )

    # Log generation
    await db["ad_mode_generation_logs"].insert_one({
        "id":              str(uuid.uuid4()),
        "user_id":         user_id,
        "campaign_id":     body.campaign_id,
        "generation_type": "full_ad_set",
        "model_used":      f"{CLAUDE_MODEL} + {DALLE_IMAGE_MODEL}",
        "request_json":    body.model_dump(),
        "response_json":   {"count": len(saved_sets)},
        "created_at":      now,
    })

    return {"ad_sets": saved_sets, "count": len(saved_sets)}


@ad_mode_router.post("/api/ad-mode/regenerate-copy")
async def regenerate_copy(
    body: RegenerateCopyRequest,
    authorization: str = Header(None),
):
    """Regenerate only the copy (hook, headline, caption, cta) for an existing ad set."""
    user = await _require_ad_mode(authorization)
    db = await _get_db()

    ad_set = await db["ad_mode_ad_sets"].find_one({
        "id":          body.ad_set_id,
        "user_id":     user["id"],
        "campaign_id": body.campaign_id,
    })
    if not ad_set:
        raise HTTPException(404, "Ad set not found")

    profile_doc = await db["ad_mode_profiles"].find_one({
        "id":      ad_set.get("business_profile_id"),
        "user_id": user["id"],
    })
    profile_data = profile_doc.get("generated_profile", {}) if profile_doc else {}
    meta = ad_set.get("metadata", {})

    concepts = await _generate_ad_concepts(
        profile=profile_data,
        goal=meta.get("goal", "awareness"),
        audience=meta.get("audience", "general"),
        tone=meta.get("tone", "professional"),
        num_concepts=1,
    )
    new_copy = concepts[0] if concepts else {}

    now = datetime.now(timezone.utc).isoformat()
    updates = {
        "hook":      new_copy.get("hook",     ad_set.get("hook", "")),
        "headline":  new_copy.get("headline", ad_set.get("headline", "")),
        "caption":   new_copy.get("caption",  ad_set.get("caption", "")),
        "cta":       new_copy.get("cta",      ad_set.get("cta", "")),
        "updated_at": now,
    }
    await db["ad_mode_ad_sets"].update_one({"id": body.ad_set_id}, {"$set": updates})
    return {"ad_set_id": body.ad_set_id, **updates}


@ad_mode_router.post("/api/ad-mode/regenerate-image")
async def regenerate_image(
    body: RegenerateImageRequest,
    authorization: str = Header(None),
):
    """Regenerate a single image for an existing ad set using DALL-E."""
    user = await _require_ad_mode(authorization)
    db = await _get_db()

    ad_set = await db["ad_mode_ad_sets"].find_one({
        "id":      body.ad_set_id,
        "user_id": user["id"],
    })
    if not ad_set:
        raise HTTPException(404, "Ad set not found")

    image_b64 = await _dalle_generate(body.image_prompt)
    now = datetime.now(timezone.utc).isoformat()

    await db["ad_mode_ad_sets"].update_one(
        {"id": body.ad_set_id},
        {"$set": {
            "image_base64":  image_b64,
            "image_prompt":  body.image_prompt,
            "updated_at":    now,
        }},
    )

    return {"ad_set_id": body.ad_set_id, "image_base64": image_b64, "updated_at": now}


@ad_mode_router.get("/api/ad-mode/assets/{ad_set_id}/download")
async def download_asset(
    ad_set_id: str,
    authorization: str = Header(None),
):
    """
    Download the generated image for an ad set as a PNG.
    Returns a JSON with the base64 image (frontend handles the download).
    """
    user = await _require_ad_mode(authorization)
    db = await _get_db()

    ad_set = await db["ad_mode_ad_sets"].find_one({
        "id":      ad_set_id,
        "user_id": user["id"],
    }, {"_id": 0})
    if not ad_set:
        raise HTTPException(404, "Ad set not found")

    image_b64 = ad_set.get("image_base64")
    if not image_b64:
        raise HTTPException(404, "No image available for this ad set")

    return {
        "ad_set_id":    ad_set_id,
        "image_base64": image_b64,
        "headline":     ad_set.get("headline", "ad"),
        "angle":        ad_set.get("angle", ""),
    }


# ---------------------------------------------------------------------------
# Campaign Lab aliases — /api/campaign-lab/* routes map to same handlers
# ---------------------------------------------------------------------------

campaign_lab_router = APIRouter(tags=["campaign-lab"])


@campaign_lab_router.get("/api/campaign-lab/status")
async def campaign_lab_status(authorization: str = Header(None)):
    return await ad_mode_status(authorization)


@campaign_lab_router.post("/api/checkout/campaign-lab")
async def checkout_campaign_lab(body: AdModeCheckoutRequest, authorization: str = Header(None)):
    return await checkout_ad_mode(body, authorization)


@campaign_lab_router.post("/api/campaign-lab/profile/generate")
async def campaign_lab_profile_generate(body: BusinessProfileInput, authorization: str = Header(None)):
    return await generate_profile(body, authorization)


@campaign_lab_router.get("/api/campaign-lab/profile")
async def campaign_lab_get_profile(authorization: str = Header(None)):
    return await get_profile(authorization)


@campaign_lab_router.put("/api/campaign-lab/profile")
async def campaign_lab_update_profile(body: UpdateProfileRequest, authorization: str = Header(None)):
    return await update_profile(body, authorization)


@campaign_lab_router.post("/api/campaign-lab/campaigns")
async def campaign_lab_create_campaign(body: CreateCampaignRequest, authorization: str = Header(None)):
    return await create_campaign(body, authorization)


@campaign_lab_router.get("/api/campaign-lab/campaigns")
async def campaign_lab_list_campaigns(authorization: str = Header(None)):
    return await list_campaigns(authorization)


@campaign_lab_router.get("/api/campaign-lab/campaigns/{campaign_id}")
async def campaign_lab_get_campaign(campaign_id: str, authorization: str = Header(None)):
    return await get_campaign(campaign_id, authorization)


@campaign_lab_router.post("/api/campaign-lab/generate")
async def campaign_lab_generate(body: GenerateAdsRequest, authorization: str = Header(None)):
    return await generate_ads(body, authorization)


@campaign_lab_router.post("/api/campaign-lab/regenerate-copy")
async def campaign_lab_regenerate_copy(body: RegenerateCopyRequest, authorization: str = Header(None)):
    return await regenerate_copy(body, authorization)


@campaign_lab_router.post("/api/campaign-lab/regenerate-image")
async def campaign_lab_regenerate_image(body: RegenerateImageRequest, authorization: str = Header(None)):
    return await regenerate_image(body, authorization)


@campaign_lab_router.get("/api/campaign-lab/assets/{ad_set_id}/download")
async def campaign_lab_download_asset(ad_set_id: str, authorization: str = Header(None)):
    return await download_asset(ad_set_id, authorization)
