"""
Full brain-chain integration test.

Tests each layer of the orchestration in sequence:
  1. Planner intent routing (unit — no backend)
  2. DALL-E image generation (requires OPENAI_API_KEY)
  3. GPT-4o image analysis (requires OPENAI_API_KEY)
  4. image_reference_generate pipeline (requires OPENAI_API_KEY)
  5. Streaming endpoint image_redirect signals (requires running backend)
  6. Non-streaming /api/chat with image (requires running backend)

Run with:
    cd backend && python -m pytest tests/test_chain.py -v -s
"""

import asyncio
import base64
import os
import sys
from pathlib import Path

import pytest

# ── Make sure backend package is importable ───────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))

OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
needs_openai = pytest.mark.skipif(not OPENAI_KEY, reason="OPENAI_API_KEY not set")
needs_anthropic = pytest.mark.skipif(not ANTHROPIC_KEY, reason="ANTHROPIC_API_KEY not set")

# ── Small but valid test image (red square, 100x100 JPEG) ────────────────────
def _make_test_image_bytes() -> bytes:
    """Create a simple 100x100 red JPEG in memory."""
    try:
        from PIL import Image as _PIL, ImageDraw as _Draw
        import io
        img = _PIL.new("RGB", (100, 100), color=(220, 50, 50))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    except ImportError:
        # Fallback: minimal valid JPEG (100x100 red square, hand-crafted b64)
        # This is a real JPEG that OpenAI vision accepts
        _b64 = (
            "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8U"
            "HRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgN"
            "DRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIy"
            "MjL/wAARCABkAGQDASIAAhEBAxEB/8QAFgABAQEAAAAAAAAAAAAAAAAABgUEA//EADAQ"
            "AAIBAwMCBgIBBQEAAAAAAAECAwAEEQUSITFBUWEGEyJxgZGhwfAyUrHh/8QAFAEBAAAA"
            "AAAAAAAAAAAAAAAA/8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAwDAQACEQMRAD8A7NUqVKl"
            "SpUqVKlSpUqVKlSpUqVKlSpUqVKlSpUqVKlSpUqVKlSpUqVKlSpUqVKlSpUqVKlSpUqV"
            "KlSpUqVKlSpUqVKlSpUqVKlSpUqVKlSpUqVKlSpUqVKlSpUqVKlSpUqVKlSpUqVKlSpU"
            "qVKlSpUqVKlSpUqVKlSpUqVKlSpUqVKlSpUqVKlSpUqVKlSpUqVKlSpUqVKlSpUqVKlS"
            "pUqVKlSpUqVKlSpUqVKlSpUqVKlSpUqVKlSpUqVKlSpUqVKlSpUqVKlSpUqVKlSpUqV"
            "Kn//2Q=="
        )
        return base64.b64decode(_b64)

_TEST_IMAGE_BYTES = _make_test_image_bytes()
_TEST_IMAGE_B64 = base64.b64encode(_TEST_IMAGE_BYTES).decode("utf-8")


# ═══════════════════════════════════════════════════════════════════════════════
# 1. PLANNER — intent routing (pure unit tests, no I/O)
# ═══════════════════════════════════════════════════════════════════════════════

class TestPlanner:
    """Verify the Phase 1 planner routes each intent correctly."""

    def _plan(self, msg, cmd=None):
        from mini_assistant.phase1.intent_planner import plan
        from mini_assistant.phase1.command_parser import ParsedCommand
        return plan(message=msg, parsed_command=cmd)

    def test_normal_chat(self):
        p = self._plan("hey how are you")
        assert p.execution_intent == "chat", f"got {p.execution_intent}"
        print(f"  [PLANNER] normal_chat -> {p.execution_intent} OK")

    def test_image_generation_keyword(self):
        p = self._plan("generate an image of a red dragon in the sky")
        assert p.execution_intent == "image_generation", f"got {p.execution_intent}"
        print(f"  [PLANNER] image_generate keyword -> {p.execution_intent} OK")

    def test_image_analysis_keyword(self):
        p = self._plan("analyze this image please")
        assert p.execution_intent == "image_analysis", f"got {p.execution_intent}"
        print(f"  [PLANNER] image_analysis keyword -> {p.execution_intent} OK")

    def test_image_reference_generate_intent(self):
        from mini_assistant.phase1.command_parser import ParsedCommand
        cmd = ParsedCommand(
            raw="make this character cooler",
            command="image",
            args="make this character cooler",
            intent_override="image_reference_generate",
            is_slash=True,
            is_known=True,
            help_requested=False,
        )
        p = self._plan("make this character cooler", cmd=cmd)
        assert p.execution_intent == "image_reference_generate", f"got {p.execution_intent}"
        assert any(t["brain"] == "vision" for t in p.sequential_tasks), "vision task missing"
        assert any(t["brain"] == "image_gen" for t in p.sequential_tasks), "image_gen task missing"
        print(f"  [PLANNER] image_reference_generate -> {p.execution_intent} OK  tasks={[t['task'] for t in p.sequential_tasks]}")

    def test_coding_intent(self):
        p = self._plan("write a python function to sort a list")
        assert p.execution_intent == "coding", f"got {p.execution_intent}"
        print(f"  [PLANNER] coding -> {p.execution_intent} OK")

    def test_debugging_intent(self):
        p = self._plan("fix this TypeError: cannot read undefined")
        assert p.execution_intent == "coding", f"got {p.execution_intent}"
        print(f"  [PLANNER] debugging -> {p.execution_intent} OK")

    def test_slash_image_command(self):
        from mini_assistant.phase1.command_parser import ParsedCommand
        cmd = ParsedCommand(
            raw="/image a sunset over mountains",
            command="image",
            args="a sunset over mountains",
            intent_override="image_generate",
            is_slash=True,
            is_known=True,
            help_requested=False,
        )
        p = self._plan("a sunset over mountains", cmd=cmd)
        assert p.execution_intent == "image_generation", f"got {p.execution_intent}"
        print(f"  [PLANNER] /image slash -> {p.execution_intent} OK")


# ═══════════════════════════════════════════════════════════════════════════════
# 2. DALL-E CLIENT — direct generation
# ═══════════════════════════════════════════════════════════════════════════════

class TestDalleClient:
    """DALL-E 3 client generates real images."""

    @needs_openai
    def test_generate_returns_base64(self):
        from image_system.services.dalle_client import DalleClient
        async def _run():
            client = DalleClient()
            b64 = await client.generate("a small red circle on a white background", quality="balanced")
            assert isinstance(b64, str) and len(b64) > 100, "empty or invalid b64"
            print(f"  [DALL-E] generate -> {len(b64)} chars b64 OK")
            return b64
        asyncio.run(_run())

    @needs_openai
    def test_health(self):
        from image_system.services.dalle_client import DalleClient
        async def _run():
            h = await DalleClient().health()
            assert h["status"] == "ok", f"health: {h}"
            print(f"  [DALL-E] health -> {h} OK")
        asyncio.run(_run())


# ═══════════════════════════════════════════════════════════════════════════════
# 3. VISION BRAIN — GPT-4o image analysis
# ═══════════════════════════════════════════════════════════════════════════════

class TestVisionBrain:
    """GPT-4o vision brain analyses an image."""

    @needs_openai
    def test_analyze_returns_text(self):
        from image_system.brains.vision_brain import VisionBrain
        async def _run():
            brain = VisionBrain()
            answer = await brain.analyze(_TEST_IMAGE_BYTES, "What color is this image?")
            assert isinstance(answer, str) and len(answer) > 5, f"bad answer: {answer!r}"
            print(f"  [VISION] analyze -> {answer[:80]!r} OK")
        asyncio.run(_run())

    @needs_openai
    def test_analyze_detailed(self):
        from image_system.brains.vision_brain import VisionBrain
        async def _run():
            brain = VisionBrain()
            desc = await brain.analyze(
                _TEST_IMAGE_BYTES,
                "Describe this image in precise visual detail: colors, content, style.",
            )
            assert isinstance(desc, str) and len(desc) > 10
            print(f"  [VISION] detailed describe -> {desc[:100]!r} OK")
        asyncio.run(_run())


# ═══════════════════════════════════════════════════════════════════════════════
# 4. FULL REFERENCE-GENERATE PIPELINE — vision -> DALL-E
# ═══════════════════════════════════════════════════════════════════════════════

class TestReferenceGeneratePipeline:
    """End-to-end: analyze image -> build prompt -> generate new image."""

    @needs_openai
    def test_full_pipeline(self):
        from image_system.brains.vision_brain import VisionBrain
        from image_system.services.dalle_client import DalleClient

        async def _run():
            # Step 1: Vision describes reference
            vision = VisionBrain()
            description = await vision.analyze(
                _TEST_IMAGE_BYTES,
                "Describe this image in precise visual detail: subject appearance, "
                "colors, art style, lighting, composition. Be specific and comprehensive.",
            )
            assert description, "empty description from vision"
            print(f"  [PIPELINE] vision description -> {description[:80]!r}")

            # Step 2: Build DALL-E prompt
            user_request = "make it blue instead of red"
            dalle_prompt = (
                f"Reference image description: {description}\n\n"
                f"User request: {user_request}\n\n"
                f"Generate a new image that fulfills the user request, visually inspired "
                f"by the reference. Preserve the art style while applying the requested changes."
            )

            # Step 3: Generate via DALL-E 3
            dalle = DalleClient()
            b64 = await dalle.generate(dalle_prompt)
            assert isinstance(b64, str) and len(b64) > 100, "empty image from DALL-E"
            print(f"  [PIPELINE] DALL-E generated -> {len(b64)} chars b64 OK")
            print(f"  [PIPELINE] FULL CHAIN PASS OK")

        asyncio.run(_run())


# ═══════════════════════════════════════════════════════════════════════════════
# 5. ROUTER BRAIN — intent classification via GPT-4o-mini
# ═══════════════════════════════════════════════════════════════════════════════

class TestRouterBrain:
    """GPT-4o-mini router classifies image generation requests."""

    @needs_openai
    def test_routes_image_request(self):
        from image_system.brains.router_brain import RouterBrain
        async def _run():
            router = RouterBrain()
            result = await router.route("draw a chibi anime villain with lightning powers")
            assert isinstance(result, dict), f"result not dict: {result}"
            intent = result.get("intent", "")
            print(f"  [ROUTER] intent={intent} checkpoint={result.get('selected_checkpoint')} OK")
        asyncio.run(_run())


# ═══════════════════════════════════════════════════════════════════════════════
# 6. BACKEND API — live endpoint tests (requires running backend)
# ═══════════════════════════════════════════════════════════════════════════════

def _backend_url():
    return (os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:7860").rstrip("/")

def _backend_reachable():
    try:
        import requests
        requests.get(f"{_backend_url()}/api/health", timeout=3)
        return True
    except Exception:
        return False

backend_up = _backend_reachable()
needs_backend = pytest.mark.skipif(not backend_up, reason="Backend not running on localhost:7860")


class TestBackendEndpoints:
    """Live API tests against the running backend."""

    @needs_backend
    def test_health(self):
        import requests
        r = requests.get(f"{_backend_url()}/api/health", timeout=5)
        assert r.status_code == 200
        data = r.json()
        print(f"  [BACKEND] health -> {data} OK")

    @needs_backend
    def test_plain_chat(self):
        import requests
        r = requests.post(
            f"{_backend_url()}/api/chat",
            json={"message": "say the word hello and nothing else", "session_id": "test-chain-001"},
            timeout=30,
        )
        assert r.status_code == 200, f"status={r.status_code} body={r.text[:200]}"
        data = r.json()
        assert "reply" in data, f"no reply key: {data.keys()}"
        print(f"  [BACKEND] /api/chat plain -> reply={data['reply'][:60]!r} OK")

    @needs_backend
    @needs_openai
    def test_image_generation_intent(self):
        """Text-to-image via DALL-E (no attachment)."""
        import requests
        r = requests.post(
            f"{_backend_url()}/api/chat",
            json={
                "message": "generate an image of a small blue circle on white background",
                "session_id": "test-chain-002",
            },
            timeout=60,
        )
        assert r.status_code == 200, f"status={r.status_code} body={r.text[:300]}"
        data = r.json()
        assert "image_base64" in data and data["image_base64"], \
            f"image_base64 missing or empty. keys={list(data.keys())}"
        print(f"  [BACKEND] image_generation -> image_base64 {len(data['image_base64'])} chars OK")

    @needs_backend
    @needs_openai
    def test_image_analysis_intent(self):
        """Attach image with describe-only request -> returns text reply, no image_base64."""
        import requests
        r = requests.post(
            f"{_backend_url()}/api/chat",
            json={
                "message": "what color is this?",
                "image_base64": _TEST_IMAGE_B64,
                "session_id": "test-chain-003",
            },
            timeout=30,
        )
        assert r.status_code == 200, f"status={r.status_code} body={r.text[:300]}"
        data = r.json()
        assert "reply" in data, f"no reply: {data.keys()}"
        assert not data.get("image_base64"), "should NOT have image_base64 for pure analysis"
        print(f"  [BACKEND] image_analysis -> reply={data['reply'][:80]!r} OK")

    @needs_backend
    @needs_openai
    def test_reference_generate_intent(self):
        """Attach image + modification keywords -> generates new image via DALL-E."""
        import requests
        r = requests.post(
            f"{_backend_url()}/api/chat",
            json={
                "message": "make this image look cooler with blue lightning effects",
                "image_base64": _TEST_IMAGE_B64,
                "session_id": "test-chain-004",
            },
            timeout=90,
        )
        assert r.status_code == 200, f"status={r.status_code} body={r.text[:300]}"
        data = r.json()
        assert "image_base64" in data and data["image_base64"], \
            f"image_base64 missing. intent={data.get('intent')} reply={data.get('reply','')[:100]}"
        print(f"  [BACKEND] image_reference_generate -> image_base64 {len(data['image_base64'])} chars OK")

    @needs_backend
    def test_stream_redirects_image_generation(self):
        """Streaming endpoint signals image_redirect for image generation requests."""
        import requests, json
        r = requests.post(
            f"{_backend_url()}/api/chat/stream",
            json={"message": "generate an image of a sunset", "session_id": "test-chain-005"},
            stream=True,
            timeout=20,
        )
        assert r.status_code == 200
        redirected = False
        for line in r.iter_lines():
            if not line:
                continue
            text = line.decode("utf-8") if isinstance(line, bytes) else line
            if text.startswith("data:"):
                try:
                    event = json.loads(text[5:])
                    if event.get("done") and event.get("meta", {}).get("type") == "image_redirect":
                        redirected = True
                        break
                except json.JSONDecodeError:
                    pass
        assert redirected, "stream did not emit image_redirect for image generation"
        print(f"  [BACKEND] stream image_generation -> image_redirect OK")

    @needs_backend
    def test_stream_redirects_reference_generate(self):
        """Streaming endpoint signals image_redirect when image + modification keywords attached."""
        import requests, json
        r = requests.post(
            f"{_backend_url()}/api/chat/stream",
            json={
                "message": "make this look cooler with lightning",
                "image_base64": _TEST_IMAGE_B64,
                "session_id": "test-chain-006",
            },
            stream=True,
            timeout=20,
        )
        assert r.status_code == 200
        redirected = False
        for line in r.iter_lines():
            if not line:
                continue
            text = line.decode("utf-8") if isinstance(line, bytes) else line
            if text.startswith("data:"):
                try:
                    event = json.loads(text[5:])
                    if event.get("done") and event.get("meta", {}).get("type") == "image_redirect":
                        redirected = True
                        break
                except json.JSONDecodeError:
                    pass
        assert redirected, "stream did not emit image_redirect for reference+generate"
        print(f"  [BACKEND] stream reference_generate -> image_redirect OK")
