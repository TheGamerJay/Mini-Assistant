"""
Mini Assistant Image System
===========================

A local image generation system using Ollama brains for routing/prompting
and ComfyUI for actual image synthesis.

Quick start::

    from backend.image_system import RouterBrain, PromptBuilder, OllamaClient, ComfyUIClient

    router = RouterBrain()
    result = await router.route("draw a shonen anime warrior")

Exported symbols
----------------
RouterBrain    – classifies user requests and selects checkpoint/workflow
PromptBuilder  – builds positive + negative prompts
ImageReviewer  – scores generated images via vision model
OllamaClient   – async Ollama REST client
ComfyUIClient  – async ComfyUI REST client
"""

from .brains.router_brain import RouterBrain
from .services.prompt_builder import PromptBuilder
from .services.image_reviewer import ImageReviewer
from .services.ollama_client import OllamaClient
from .services.comfyui_client import ComfyUIClient

__all__ = [
    "RouterBrain",
    "PromptBuilder",
    "ImageReviewer",
    "OllamaClient",
    "ComfyUIClient",
]

__version__ = "1.0.0"
