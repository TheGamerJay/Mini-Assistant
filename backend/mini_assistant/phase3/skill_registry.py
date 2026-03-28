"""
skill_registry.py — Skill Library
───────────────────────────────────
Defines reusable, inspectable workflow recipes that the Skill Selector
can match to Planner output.

Each Skill specifies:
  name             — snake_case unique identifier
  description      — human-readable purpose
  intents          — which Phase 1 Planner intents this skill handles
  trigger_patterns — regex patterns whose match boosts confidence
  required_brains  — brains that must be available for this skill
  required_tools   — tools that must be available
  input_fields     — expected fields in the request
  steps            — ordered execution steps (override Planner generic tasks)
  output_fields    — expected fields in the result
  fallback         — behaviour if skill execution fails
  validation_rules — what the Critic should check
  min_confidence   — minimum score to activate this skill (0.0–1.0)
  category         — "standard" | "3d"
  status           — "active" | "stub"  (3D skills are stubs until Phase 9)

Blueprint rules honoured:
  - Skills do NOT replace the Planner — they refine its output
  - Skills do NOT auto-rewrite code silently
  - Learning is lightweight and inspectable
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# ── Skill data type ───────────────────────────────────────────────────────────

@dataclass
class Skill:
    name:             str
    description:      str
    intents:          list[str]
    trigger_patterns: list[str]          = field(default_factory=list)
    required_brains:  list[str]          = field(default_factory=list)
    required_tools:   list[str]          = field(default_factory=list)
    input_fields:     list[str]          = field(default_factory=list)
    steps:            list[dict]         = field(default_factory=list)
    output_fields:    list[str]          = field(default_factory=list)
    fallback:         str                = "fall_through_to_planner"
    validation_rules: list[str]          = field(default_factory=list)
    min_confidence:   float              = 0.50
    category:         str                = "standard"
    status:           str                = "active"

    # Compiled patterns (populated by registry on registration)
    _compiled: list = field(default_factory=list, repr=False)

    def compile_patterns(self) -> None:
        self._compiled = [re.compile(p, re.IGNORECASE) for p in self.trigger_patterns]

    def pattern_matches(self, message: str) -> bool:
        return any(p.search(message) for p in self._compiled)

    def to_dict(self) -> dict:
        return {
            "name":             self.name,
            "description":      self.description,
            "intents":          self.intents,
            "trigger_patterns": self.trigger_patterns,
            "required_brains":  self.required_brains,
            "required_tools":   self.required_tools,
            "input_fields":     self.input_fields,
            "steps":            self.steps,
            "output_fields":    self.output_fields,
            "fallback":         self.fallback,
            "validation_rules": self.validation_rules,
            "min_confidence":   self.min_confidence,
            "category":         self.category,
            "status":           self.status,
        }


# ── Registry ──────────────────────────────────────────────────────────────────

_REGISTRY: dict[str, Skill] = {}


def register(skill: Skill) -> Skill:
    """Register a skill and compile its patterns."""
    skill.compile_patterns()
    _REGISTRY[skill.name] = skill
    return skill


def get(name: str) -> Optional[Skill]:
    return _REGISTRY.get(name)


def all_skills() -> list[Skill]:
    return list(_REGISTRY.values())


def skills_for_intent(intent: str) -> list[Skill]:
    return [s for s in _REGISTRY.values() if intent in s.intents]


def active_skills() -> list[Skill]:
    return [s for s in _REGISTRY.values() if s.status == "active"]


# ─────────────────────────────────────────────────────────────────────────────
# STANDARD SKILLS
# ─────────────────────────────────────────────────────────────────────────────

register(Skill(
    name        = "build_landing_page",
    description = "Generate a complete, polished landing page (HTML/CSS/JS) for a product or service.",
    intents     = ["app_builder"],
    trigger_patterns = [
        r"\blanding page\b",
        r"\bhero section\b",
        r"\bproduct page\b",
        r"\bmarketing (page|site)\b",
    ],
    required_brains  = ["coding", "research"],
    input_fields     = ["product_name", "value_proposition", "cta_text"],
    steps = [
        {"id": "s1", "task": "gather_product_requirements",  "brain": "research", "depends_on": []},
        {"id": "s2", "task": "design_section_layout",        "brain": "research", "depends_on": ["s1"]},
        {"id": "s3", "task": "generate_html_css_js",         "brain": "coding",   "depends_on": ["s2"]},
        {"id": "s4", "task": "critic_validate_output",       "brain": "critic",   "depends_on": ["s3"]},
    ],
    output_fields    = ["html", "css", "js", "preview_url"],
    fallback         = "fall_through_to_planner",
    validation_rules = ["output contains <!DOCTYPE html>", "output contains <section", "no broken JS"],
    min_confidence   = 0.55,
    category         = "standard",
    status           = "active",
))

register(Skill(
    name        = "generate_project_logo",
    description = "Generate a logo image for a project or product via DALL-E 3.",
    intents     = ["image_generate"],
    trigger_patterns = [
        r"\b(project|app|product|company|brand|startup)\s+(logo|icon|brand)\b",
        r"\blogo\s+for\b",
        r"\bdesign\s+(a\s+)?(logo|icon|brand identity)\b",
    ],
    required_brains = ["image_gen"],
    input_fields    = ["project_name", "style_keywords"],
    steps = [
        {"id": "s1", "task": "build_logo_prompt",            "brain": "fast",      "depends_on": []},
        {"id": "s2", "task": "generate_logo_512x512",        "brain": "image_gen", "depends_on": ["s1"]},
        {"id": "s3", "task": "review_logo_quality",          "brain": "critic",    "depends_on": ["s2"]},
    ],
    output_fields    = ["image_base64", "prompt_used"],
    fallback         = "fall_through_to_planner",
    validation_rules = ["image_base64 is present and non-empty"],
    min_confidence   = 0.60,
    category         = "standard",
    status           = "active",
))

register(Skill(
    name        = "analyze_ui_screenshot",
    description = "Analyze a UI screenshot and provide specific, actionable UX feedback.",
    intents     = ["image_analysis"],
    trigger_patterns = [
        r"\b(ui|ux|interface|design|screen|screenshot|layout|figma|wireframe)\b",
        r"\b(review|critique|feedback|improve)\b.{0,30}\b(design|layout|ui|ux)\b",
        r"\bwhat.?s wrong with\b.{0,30}\b(ui|design|layout|screen)\b",
    ],
    required_brains = ["vision", "research"],
    input_fields    = ["image_base64", "question"],
    steps = [
        {"id": "s1", "task": "analyse_ui_with_vision",       "brain": "vision",    "depends_on": []},
        {"id": "s2", "task": "synthesise_ux_feedback",       "brain": "research",  "depends_on": ["s1"]},
        {"id": "s3", "task": "format_actionable_suggestions","brain": "fast",      "depends_on": ["s2"]},
    ],
    output_fields    = ["feedback", "issues", "suggestions"],
    fallback         = "fall_through_to_planner",
    validation_rules = ["response mentions specific UI elements", "response length > 100 chars"],
    min_confidence   = 0.55,
    category         = "standard",
    status           = "active",
))

register(Skill(
    name        = "fix_import_error",
    description = "Diagnose and fix Python ImportError / ModuleNotFoundError issues.",
    intents     = ["debugging"],
    trigger_patterns = [
        r"\b(ImportError|ModuleNotFoundError|No module named|cannot import name)\b",
        r"\bimport (error|problem|issue|fail)\b",
        r"\bmodule.*not (found|installed)\b",
    ],
    required_brains = ["coding"],
    input_fields    = ["error_message", "file_path"],
    steps = [
        {"id": "s1", "task": "identify_missing_module",      "brain": "coding",   "depends_on": []},
        {"id": "s2", "task": "check_requirements_txt",       "tool": "file_read", "depends_on": ["s1"]},
        {"id": "s3", "task": "propose_install_command",      "brain": "coding",   "depends_on": ["s1", "s2"]},
        {"id": "s4", "task": "critic_validate_fix",          "brain": "critic",   "depends_on": ["s3"]},
    ],
    output_fields    = ["diagnosis", "fix_command", "requirements_update"],
    fallback         = "fall_through_to_planner",
    validation_rules = ["fix_command contains pip install", "response mentions specific module name"],
    min_confidence   = 0.70,
    category         = "standard",
    status           = "active",
))

register(Skill(
    name        = "wire_mic_button",
    description = "Wire the microphone button to speech-to-text and insert transcript into chat input.",
    intents     = ["code_runner", "debugging"],
    trigger_patterns = [
        r"\bmic(rophone)?\s*button\b",
        r"\bvoice\s*(input|button|recording)\b",
        r"\bspeech.?to.?text\b",
        r"\baudio\s*(input|recording|capture)\b",
        r"\brecord(ing)?\s*(button|mic)\b",
    ],
    required_brains = ["coding"],
    input_fields    = ["component_file", "hook_file"],
    steps = [
        {"id": "s1", "task": "inspect_chat_input_component",  "tool": "file_read", "depends_on": []},
        {"id": "s2", "task": "inspect_voice_hook_or_component","tool": "file_read", "depends_on": []},
        {"id": "s3", "task": "write_stt_integration_patch",   "brain": "coding",   "depends_on": ["s1", "s2"]},
        {"id": "s4", "task": "critic_validate_patch",         "brain": "critic",   "depends_on": ["s3"]},
    ],
    output_fields    = ["patch", "files_to_modify"],
    fallback         = "fall_through_to_planner",
    validation_rules = ["patch targets ChatInput.js or VoiceControl.js", "no duplicate MediaRecorder init"],
    min_confidence   = 0.65,
    category         = "standard",
    status           = "active",
))

register(Skill(
    name        = "export_project_zip",
    description = "Export an App Builder project as a ZIP archive.",
    intents     = ["app_builder", "file_analysis"],
    trigger_patterns = [
        r"\bexport\s*(as\s*)?(zip|archive|download)\b",
        r"\bdownload\s*(the\s*)?(project|app|files|code)\b",
        r"\bzip\s*(the\s*)?(project|app|files)\b",
    ],
    required_tools  = ["file_read"],
    input_fields    = ["project_id", "project_tree"],
    steps = [
        {"id": "s1", "task": "collect_project_files",         "tool": "file_read", "depends_on": []},
        {"id": "s2", "task": "package_as_zip",                "tool": "python",    "depends_on": ["s1"]},
    ],
    output_fields    = ["zip_bytes", "filename"],
    fallback         = "fall_through_to_planner",
    validation_rules = ["zip file contains index.html"],
    min_confidence   = 0.70,
    category         = "standard",
    status           = "active",
))

register(Skill(
    name        = "push_to_github",
    description = "Commit current App Builder project files and push to a GitHub repository.",
    intents     = ["app_builder", "code_runner"],
    trigger_patterns = [
        r"\bpush\s*(to\s*)?(github|git|repo(sitory)?)\b",
        r"\bgit\s*push\b",
        r"\bcommit\s*(and\s*)?push\b",
        r"\bpublish\s*(to\s*)?github\b",
    ],
    required_tools  = ["python"],
    input_fields    = ["github_token", "repo_url", "project_files"],
    steps = [
        {"id": "s1", "task": "validate_github_credentials",  "brain": "fast",     "depends_on": []},
        {"id": "s2", "task": "prepare_commit_payload",       "brain": "coding",   "depends_on": ["s1"]},
        {"id": "s3", "task": "push_to_github_api",           "tool": "python",    "depends_on": ["s2"]},
    ],
    output_fields    = ["repo_url", "commit_sha", "pr_url"],
    fallback         = "fall_through_to_planner",
    validation_rules = ["response includes repo URL or commit reference"],
    min_confidence   = 0.70,
    category         = "standard",
    status           = "active",
))


# ─────────────────────────────────────────────────────────────────────────────
# 3D SKILLS  (status = "stub" — active in Phase 9)
# ─────────────────────────────────────────────────────────────────────────────

for _skill in [
    Skill(
        name        = "generate_3d_character_from_image",
        description = "Convert a reference image into a rigged, game-ready 3D character.",
        intents     = ["3d_character_generation"],
        trigger_patterns = [r"\b3d\b.{0,30}\b(character|hero|player|avatar)\b.{0,30}\bfrom\s*(this\s*)?(image|photo|reference)\b"],
        required_brains  = ["vision", "3d_gen", "3d_cleanup"],
        steps = [
            {"id": "s1", "task": "analyse_reference_image",   "brain": "vision",      "depends_on": []},
            {"id": "s2", "task": "3d_concept_generation",     "brain": "3d_concept",  "depends_on": ["s1"]},
            {"id": "s3", "task": "3d_mesh_generation",        "brain": "3d_gen",      "depends_on": ["s2"]},
            {"id": "s4", "task": "mesh_cleanup",              "brain": "3d_cleanup",  "depends_on": ["s3"]},
            {"id": "s5", "task": "auto_rig",                  "brain": "3d_rig",      "depends_on": ["s4"]},
            {"id": "s6", "task": "validate_game_ready",       "brain": "critic",      "depends_on": ["s5"]},
        ],
        category = "3d", status = "stub",
    ),
    Skill(
        name        = "generate_3d_character_from_prompt",
        description = "Generate a rigged 3D character from a text description.",
        intents     = ["3d_character_generation"],
        trigger_patterns = [r"\bgenerate\b.{0,30}\b3d\b.{0,30}\b(character|hero|player|enemy|npc)\b"],
        required_brains  = ["research", "3d_gen", "3d_cleanup"],
        steps = [
            {"id": "s1", "task": "concept_art_generation",    "brain": "image_gen",   "depends_on": []},
            {"id": "s2", "task": "3d_mesh_generation",        "brain": "3d_gen",      "depends_on": ["s1"]},
            {"id": "s3", "task": "mesh_cleanup",              "brain": "3d_cleanup",  "depends_on": ["s2"]},
            {"id": "s4", "task": "auto_rig",                  "brain": "3d_rig",      "depends_on": ["s3"]},
            {"id": "s5", "task": "validate_game_ready",       "brain": "critic",      "depends_on": ["s4"]},
        ],
        category = "3d", status = "stub",
    ),
    Skill(name="cleanup_generated_mesh",       description="Clean up a raw generated 3D mesh.",      intents=["3d_asset_generation","3d_character_generation"], trigger_patterns=[r"\bclean\s*(up\s*)?mesh\b", r"\bmesh\s*(repair|fix|cleanup)\b"],    required_brains=["3d_cleanup"], steps=[{"id":"s1","task":"cleanup_mesh","brain":"3d_cleanup","depends_on":[]}], category="3d", status="stub"),
    Skill(name="auto_rig_character",           description="Automatically rig a 3D character mesh.", intents=["3d_character_generation"],                      trigger_patterns=[r"\b(auto[_-]?rig|add rig|rigging|armature)\b"],                 required_brains=["3d_rig"],     steps=[{"id":"s1","task":"auto_rig","brain":"3d_rig","depends_on":[]}],           category="3d", status="stub"),
    Skill(name="apply_basic_animation_pack",   description="Apply idle/walk/run/jump/attack anims.", intents=["3d_character_generation"],                      trigger_patterns=[r"\b(animat|idle|walk cycle|run cycle|attack anim)\b"],          required_brains=["3d_anim"],    steps=[{"id":"s1","task":"apply_anim_pack","brain":"3d_anim","depends_on":[]}],   category="3d", status="stub"),
    Skill(name="validate_game_ready_character",description="Validate rig, textures, anims.",          intents=["3d_character_generation","3d_asset_generation"],trigger_patterns=[r"\b(validate|check|verify)\b.{0,30}\b(3d|character|rig|mesh)\b"], required_brains=["critic"],    steps=[{"id":"s1","task":"validate_asset","brain":"critic","depends_on":[]}],     category="3d", status="stub"),
    Skill(name="preview_3d_character",         description="Render a preview thumbnail.",             intents=["3d_character_generation"],                      trigger_patterns=[r"\b(preview|thumbnail|render|turntable)\b.{0,20}\b3d\b"],       required_brains=["3d_preview"], steps=[{"id":"s1","task":"render_preview","brain":"3d_preview","depends_on":[]}],  category="3d", status="stub"),
    Skill(name="inject_character_into_game",   description="Package asset for App Builder game use.", intents=["3d_character_generation","app_builder"],       trigger_patterns=[r"\binject\b.{0,30}\b(into|in)\b.{0,20}\b(game|app|builder)\b"],required_brains=["3d_inject"],  steps=[{"id":"s1","task":"inject_asset","brain":"3d_inject","depends_on":[]}],    category="3d", status="stub"),
    Skill(name="generate_enemy_character",     description="Generate a 3D enemy character.",          intents=["3d_character_generation"],                      trigger_patterns=[r"\benemy\b.{0,30}\b(character|3d|model|generate)\b"],           required_brains=["3d_gen"],     steps=[{"id":"s1","task":"generate_enemy","brain":"3d_gen","depends_on":[]}],     category="3d", status="stub"),
    Skill(name="generate_npc_character",       description="Generate a 3D NPC character.",            intents=["3d_character_generation"],                      trigger_patterns=[r"\bnpc\b.{0,30}\b(character|3d|model|generate)\b"],             required_brains=["3d_gen"],     steps=[{"id":"s1","task":"generate_npc","brain":"3d_gen","depends_on":[]}],       category="3d", status="stub"),
]:
    register(_skill)
