"""
Strict JSON schema validation for all brain responses.
If the LLM returns invalid or incomplete JSON, this module:
  1. Tries multiple extraction strategies (direct, markdown block, regex, cleanup)
  2. Validates required fields against a schema
  3. Fills in defaults for missing optional fields
  4. Builds a repair prompt for a one-shot retry
"""
import json
import re
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Schemas ────────────────────────────────────────────────────────────────────

ROUTER_SCHEMA: Dict = {
    "required": [
        "intent", "style_family", "selected_checkpoint",
        "selected_workflow", "confidence",
    ],
    "optional": [
        "anime_genre", "visual_mode", "needs_reference_analysis",
        "needs_upscale", "needs_face_detail",
        "anime_score", "realism_score", "fantasy_score",
    ],
    "defaults": {
        "anime_genre": "general",
        "visual_mode": "portrait",
        "needs_reference_analysis": False,
        "needs_upscale": False,
        "needs_face_detail": False,
        "anime_score": 0.5,
        "realism_score": 0.5,
        "fantasy_score": 0.5,
        "confidence": 0.5,
    },
}

VISION_SCHEMA: Dict = {
    "required": ["quality_score", "style_match", "retry_recommended"],
    "optional": [
        "anatomy_score", "composition_score", "issues",
        "retry_reason", "alt_checkpoint", "alt_workflow", "confidence",
    ],
    "defaults": {
        "anatomy_score": 0.7,
        "composition_score": 0.7,
        "issues": [],
        "retry_reason": None,
        "alt_checkpoint": None,
        "alt_workflow": None,
        "confidence": 0.7,
    },
}

CRITIC_SCHEMA: Dict = {
    "required": ["should_retry"],
    "optional": ["adjusted_params", "alt_checkpoint", "alt_workflow", "reason"],
    "defaults": {
        "adjusted_params": {},
        "alt_checkpoint": None,
        "alt_workflow": None,
        "reason": "No issues detected",
    },
}


# ── JSON extraction ────────────────────────────────────────────────────────────

def extract_json_from_text(text: str) -> Optional[Dict]:
    """Try multiple strategies to extract a JSON object from LLM output."""
    if not text:
        return None
    text = text.strip()

    # Strategy 1: direct parse
    try:
        return json.loads(text)
    except Exception:
        pass

    # Strategy 2: markdown JSON block  ```json { ... } ```
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass

    # Strategy 3: first { ... } block in the text
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass

    # Strategy 4: common LLM mistakes — trailing commas, single quotes
    cleaned = re.sub(r",\s*([}\]])", r"\1", text)
    cleaned = cleaned.replace("'", '"')
    try:
        return json.loads(cleaned)
    except Exception:
        pass

    # Strategy 5: try to fix unquoted keys
    try:
        fixed = re.sub(r"(\w+):", r'"\1":', cleaned)
        return json.loads(fixed)
    except Exception:
        pass

    logger.debug("json_validator: all extraction strategies failed for text: %s", text[:200])
    return None


# ── Schema validation ──────────────────────────────────────────────────────────

def validate_and_fill(
    data: Dict, schema: Dict, schema_name: str
) -> Tuple[Dict, List[str]]:
    """
    Validate required fields are present; fill defaults for missing optional fields.
    Returns (filled_data, list_of_errors).
    """
    errors: List[str] = []

    if not isinstance(data, dict):
        return {}, [f"{schema_name}: response is not a dict, got {type(data).__name__}"]

    for field in schema["required"]:
        if field not in data:
            errors.append(f"{schema_name}: missing required field '{field}'")

    # Fill defaults for missing optional/default fields
    for field, default in schema.get("defaults", {}).items():
        if field not in data:
            data[field] = default

    return data, errors


def parse_and_validate(
    text: str, schema: Dict, schema_name: str
) -> Tuple[Optional[Dict], List[str]]:
    """
    Full pipeline: extract JSON → validate schema → fill defaults.
    Returns (data_or_None, list_of_errors).
    """
    data = extract_json_from_text(text)
    if data is None:
        return None, [f"{schema_name}: could not extract valid JSON from LLM response"]
    data, errors = validate_and_fill(data, schema, schema_name)
    if errors:
        logger.warning("json_validator [%s] errors: %s", schema_name, errors)
    return data, errors


# ── Repair prompt ──────────────────────────────────────────────────────────────

def build_repair_prompt(
    original_prompt: str, bad_response: str, schema: Dict, schema_name: str
) -> str:
    """
    Build a repair prompt to send back to the model when the first response
    could not be parsed as valid JSON.
    """
    required = schema["required"]
    defaults = schema.get("defaults", {})
    example: Dict[str, Any] = {f: "..." for f in required}
    example.update({k: v for k, v in defaults.items() if k not in example})

    return (
        f"Your previous response could not be parsed as valid JSON.\n\n"
        f"Required fields for {schema_name}: {required}\n\n"
        f"Your previous response (first 400 chars):\n{bad_response[:400]}\n\n"
        f"Please respond with ONLY a valid JSON object — no markdown, no explanation, "
        f"no extra text. At minimum include all required fields.\n\n"
        f"Example format:\n{json.dumps(example, indent=2)}\n\n"
        f"Original request (first 300 chars):\n{original_prompt[:300]}"
    )
