"""
Data models for the image CEO orchestration pipeline.
All brains communicate through these typed structures.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ImageTaskRequest:
    """Raw request entering the CEO pipeline."""
    user_message: str
    session_id: str
    image_bytes: bytes | None = None
    model_preference: str | None = None


@dataclass
class EditStep:
    """One atomic edit operation from the Edit Planner Brain."""
    edit_type: str                          # "color_change" | "structural_edit"
    region_description: str = ""
    from_color: str | None = None
    to_color: str | None = None
    mask_box: dict | None = None
    allow_reconstruction: bool = True
    preserve_regions: list[str] = field(default_factory=list)
    final_instruction: str | None = None
    color_overlap_risk: bool = False


@dataclass
class RegionScanResult:
    """Output from the Analysis Brain's region scan."""
    mask_box: dict | None = None
    preserve_elements: list[str] = field(default_factory=list)
    cached_description: str | None = None
    refined_mask_bytes: bytes | None = None


@dataclass
class TierResult:
    """Output from the Image Execution Brain (T1/T2/T3)."""
    success: bool
    b64: str | None = None
    image_bytes: bytes | None = None
    method_used: str = "unknown"
    source_preserved: bool = False
    reconstruction_fallback: bool = False
    confidence: float = 0.0
    tier_errors: list[str] = field(default_factory=list)
    t2_diagnosis: dict | None = None   # populated on T2 no_op, consumed by T3 + QA


@dataclass
class QAResult:
    """Output from the QA Brain."""
    passed: bool
    status: str = "unknown"            # "success" | "no_op" | "partial"
    target_change_score: float = 0.0
    preserve_integrity_score: float = 1.0
    changed_pixels: int = 0
    failure_code: str | None = None
    detected_color: str | None = None
    failure_reason: str = ""
    suggested_retries: list[str] = field(default_factory=list)
    user_message: str = ""


@dataclass
class SessionContext:
    """Mutable context maintained across edit steps by the Memory Brain."""
    session_id: str
    cached_description: str | None = None
    preserve_elements: list[str] = field(default_factory=list)


@dataclass
class ImageTaskResult:
    """Final result returned from the CEO to the API layer."""
    success: bool
    image_b64: str | None = None
    reply: str = ""
    metadata: dict = field(default_factory=dict)
    suggested_retries: list[str] = field(default_factory=list)
    attempt_count: int = 1
