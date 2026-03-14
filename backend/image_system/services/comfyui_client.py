"""
Async ComfyUI API client for the Mini Assistant image system.

Handles workflow queueing, progress polling, image retrieval, and provides
a build_standard_workflow helper that constructs a valid txt2img workflow
without requiring external JSON files.
"""

import asyncio
import copy
import json
import logging
import os
import random
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)

# Path to the bundled workflow JSON files
_WORKFLOWS_DIR = Path(__file__).parent.parent / "config" / "workflows"


class ComfyUIError(Exception):
    """Raised when ComfyUI returns an error or a timeout occurs."""


class ComfyUIClient:
    """
    Async client for the ComfyUI REST + WebSocket API.

    Usage::

        client = ComfyUIClient()
        images = await client.generate(workflow_dict)
        # images is a list of raw PNG bytes
    """

    def __init__(self, base_url: str = os.environ.get("COMFYUI_URL", "http://localhost:8188")) -> None:
        self.base_url = base_url.rstrip("/")
        self._session: Optional[aiohttp.ClientSession] = None

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    # ------------------------------------------------------------------
    # Queue & history
    # ------------------------------------------------------------------

    async def queue_prompt(
        self, workflow_dict: dict, client_id: Optional[str] = None
    ) -> str:
        """
        Submit a workflow to the ComfyUI prompt queue.

        Args:
            workflow_dict: ComfyUI API-format workflow (node-id keyed dict).
            client_id: Optional UUID string to tag the request.

        Returns:
            The ``prompt_id`` string assigned by ComfyUI.
        """
        cid = client_id or str(uuid.uuid4())
        payload = {"prompt": workflow_dict, "client_id": cid}
        session = await self._get_session()
        url = f"{self.base_url}/prompt"

        logger.debug("Queuing prompt client_id=%s nodes=%d", cid, len(workflow_dict))

        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise ComfyUIError(f"queue_prompt HTTP {resp.status}: {body[:200]}")
            data = await resp.json()

        prompt_id: str = data["prompt_id"]
        logger.info("Queued prompt_id=%s", prompt_id)
        return prompt_id

    async def get_history(self, prompt_id: str) -> dict:
        """
        Fetch the execution history entry for *prompt_id*.

        Returns:
            The history dict for this prompt, or an empty dict if not found.
        """
        session = await self._get_session()
        url = f"{self.base_url}/history/{prompt_id}"
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            resp.raise_for_status()
            data = await resp.json()
        return data.get(prompt_id, {})

    async def wait_for_completion(
        self, prompt_id: str, timeout: int = 300, poll_interval: float = 2.0
    ) -> dict:
        """
        Poll /history until the prompt finishes or times out.

        Args:
            prompt_id: The ID returned by queue_prompt.
            timeout: Maximum wait in seconds.
            poll_interval: Seconds between polls.

        Returns:
            The history outputs dict on success.

        Raises:
            ComfyUIError: On timeout or detected error.
        """
        deadline = asyncio.get_event_loop().time() + timeout
        logger.info("Waiting for prompt_id=%s (timeout=%ds)", prompt_id, timeout)

        while asyncio.get_event_loop().time() < deadline:
            history = await self.get_history(prompt_id)
            if history:
                # Check for errors reported in the history
                if "error" in history or history.get("status", {}).get("status_str") == "error":
                    raise ComfyUIError(f"ComfyUI reported error for {prompt_id}: {history}")
                outputs = history.get("outputs", {})
                if outputs:
                    logger.info("Prompt %s completed with %d output nodes", prompt_id, len(outputs))
                    return outputs
            await asyncio.sleep(poll_interval)

        raise ComfyUIError(f"Timed out waiting for prompt_id={prompt_id} after {timeout}s")

    # ------------------------------------------------------------------
    # Image retrieval
    # ------------------------------------------------------------------

    async def get_image(
        self, filename: str, subfolder: str = "", folder_type: str = "output"
    ) -> bytes:
        """
        Download a generated image from ComfyUI's /view endpoint.

        Args:
            filename: File name as reported in history outputs.
            subfolder: Subfolder within the output directory.
            folder_type: Usually "output".

        Returns:
            Raw image bytes (PNG).
        """
        session = await self._get_session()
        params = {"filename": filename, "subfolder": subfolder, "type": folder_type}
        url = f"{self.base_url}/view"
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=60)) as resp:
            resp.raise_for_status()
            return await resp.read()

    # ------------------------------------------------------------------
    # High-level generate
    # ------------------------------------------------------------------

    async def generate(self, workflow_dict: dict, timeout: int = 300) -> List[bytes]:
        """
        Complete generation pipeline: queue → wait → download images.

        Args:
            workflow_dict: ComfyUI API workflow dict.
            timeout: Total seconds to wait for completion.

        Returns:
            List of raw PNG bytes, one per generated image.
        """
        prompt_id = await self.queue_prompt(workflow_dict)
        outputs = await self.wait_for_completion(prompt_id, timeout=timeout)

        images: List[bytes] = []
        for node_id, node_output in outputs.items():
            for img_info in node_output.get("images", []):
                img_bytes = await self.get_image(
                    filename=img_info["filename"],
                    subfolder=img_info.get("subfolder", ""),
                    folder_type=img_info.get("type", "output"),
                )
                images.append(img_bytes)
                logger.debug("Downloaded image %s (%d bytes)", img_info["filename"], len(img_bytes))

        logger.info("generate() returned %d images for prompt_id=%s", len(images), prompt_id)
        return images

    # ------------------------------------------------------------------
    # Queue status & interrupt
    # ------------------------------------------------------------------

    async def get_queue_status(self) -> dict:
        """Return the current ComfyUI queue status."""
        session = await self._get_session()
        url = f"{self.base_url}/queue"
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def interrupt(self) -> None:
        """Send an interrupt signal to stop the current ComfyUI generation."""
        session = await self._get_session()
        url = f"{self.base_url}/interrupt"
        async with session.post(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            resp.raise_for_status()
        logger.info("Interrupt sent to ComfyUI")

    # ------------------------------------------------------------------
    # Workflow helpers
    # ------------------------------------------------------------------

    def load_workflow(self, workflow_name: str) -> dict:
        """
        Load a workflow JSON file from the config/workflows directory.

        Args:
            workflow_name: Base name of the workflow (with or without .json).

        Returns:
            The workflow dict (deep copy so the caller can mutate it freely).
        """
        if not workflow_name.endswith(".json"):
            workflow_name += ".json"
        path = _WORKFLOWS_DIR / workflow_name
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return copy.deepcopy(data)

    def inject_params(self, workflow_dict: dict, params_dict: dict) -> dict:
        """
        Deep-inject generation parameters into a ComfyUI workflow dict.

        Matches nodes by their ``_meta.title`` or ``class_type``.

        Supported param keys and their targets:
        - ``positive_prompt``  → CLIPTextEncode positive node ``text``
        - ``negative_prompt``  → CLIPTextEncode negative node ``text``
        - ``checkpoint``       → CheckpointLoaderSimple ``ckpt_name``
        - ``width``            → EmptyLatentImage ``width``
        - ``height``           → EmptyLatentImage ``height``
        - ``steps``            → KSampler ``steps``
        - ``cfg``              → KSampler ``cfg``
        - ``seed``             → KSampler ``seed``
        - ``sampler``          → KSampler ``sampler_name``
        - ``scheduler``        → KSampler ``scheduler``
        - ``denoise``          → KSampler ``denoise``
        - ``filename_prefix``  → SaveImage ``filename_prefix``

        Args:
            workflow_dict: Workflow to mutate (in-place copy returned).
            params_dict: Parameter overrides.

        Returns:
            Modified workflow dict (same object, mutated in place).
        """
        wf = copy.deepcopy(workflow_dict)

        for node_id, node in wf.items():
            inputs: dict = node.get("inputs", {})
            title: str = node.get("_meta", {}).get("title", "")
            class_type: str = node.get("class_type", "")

            # CheckpointLoaderSimple
            if class_type == "CheckpointLoaderSimple" or title == "CheckpointLoaderSimple":
                if "checkpoint" in params_dict:
                    inputs["ckpt_name"] = params_dict["checkpoint"]

            # Positive CLIP
            elif class_type == "CLIPTextEncode" and "positive" in title.lower():
                if "positive_prompt" in params_dict:
                    inputs["text"] = params_dict["positive_prompt"]

            # Negative CLIP
            elif class_type == "CLIPTextEncode" and "negative" in title.lower():
                if "negative_prompt" in params_dict:
                    inputs["text"] = params_dict["negative_prompt"]

            # EmptyLatentImage
            elif class_type == "EmptyLatentImage":
                if "width" in params_dict:
                    inputs["width"] = int(params_dict["width"])
                if "height" in params_dict:
                    inputs["height"] = int(params_dict["height"])

            # KSampler
            elif class_type == "KSampler":
                for key, field in [
                    ("steps", "steps"),
                    ("cfg", "cfg"),
                    ("seed", "seed"),
                    ("sampler", "sampler_name"),
                    ("scheduler", "scheduler"),
                    ("denoise", "denoise"),
                ]:
                    if key in params_dict:
                        inputs[field] = params_dict[key]

            # SaveImage
            elif class_type == "SaveImage":
                if "filename_prefix" in params_dict:
                    inputs["filename_prefix"] = params_dict["filename_prefix"]

            # LoadImage (init / reference image)
            elif class_type == "LoadImage" and "init_image_filename" in params_dict:
                # Only inject if this is NOT the mask node
                if "mask" not in title.lower():
                    inputs["image"] = params_dict["init_image_filename"]

            # LoadImage used as mask (title contains "mask")
            elif class_type == "LoadImage" and "mask_image_filename" in params_dict:
                if "mask" in title.lower():
                    inputs["image"] = params_dict["mask_image_filename"]

            node["inputs"] = inputs

        return wf

    def build_standard_workflow(
        self,
        checkpoint: str,
        positive_prompt: str,
        negative_prompt: str,
        width: int = 512,
        height: int = 512,
        steps: int = 28,
        cfg: float = 7.0,
        seed: Optional[int] = None,
        sampler: str = "dpmpp_2m",
        scheduler: str = "karras",
    ) -> dict:
        """
        Build a complete txt2img ComfyUI workflow dict from scratch.

        This does not require any JSON workflow file on disk.

        Args:
            checkpoint: Model filename (e.g. "animagine-xl-4.0.safetensors").
            positive_prompt: Positive text prompt.
            negative_prompt: Negative text prompt.
            width: Image width in pixels.
            height: Image height in pixels.
            steps: Number of sampling steps.
            cfg: CFG scale.
            seed: Random seed; if None, a random one is chosen.
            sampler: KSampler sampler name.
            scheduler: KSampler scheduler name.

        Returns:
            ComfyUI API-format workflow dict ready to pass to queue_prompt.
        """
        if seed is None:
            seed = random.randint(0, 2**32 - 1)

        workflow: Dict[str, Any] = {
            "1": {
                "inputs": {"ckpt_name": checkpoint},
                "class_type": "CheckpointLoaderSimple",
                "_meta": {"title": "CheckpointLoaderSimple"},
            },
            "2": {
                "inputs": {"text": positive_prompt, "clip": ["1", 1]},
                "class_type": "CLIPTextEncode",
                "_meta": {"title": "CLIPTextEncode positive"},
            },
            "3": {
                "inputs": {"text": negative_prompt, "clip": ["1", 1]},
                "class_type": "CLIPTextEncode",
                "_meta": {"title": "CLIPTextEncode negative"},
            },
            "4": {
                "inputs": {"width": width, "height": height, "batch_size": 1},
                "class_type": "EmptyLatentImage",
                "_meta": {"title": "EmptyLatentImage"},
            },
            "5": {
                "inputs": {
                    "seed": seed,
                    "steps": steps,
                    "cfg": cfg,
                    "sampler_name": sampler,
                    "scheduler": scheduler,
                    "denoise": 1.0,
                    "model": ["1", 0],
                    "positive": ["2", 0],
                    "negative": ["3", 0],
                    "latent_image": ["4", 0],
                },
                "class_type": "KSampler",
                "_meta": {"title": "KSampler"},
            },
            "6": {
                "inputs": {"samples": ["5", 0], "vae": ["1", 2]},
                "class_type": "VAEDecode",
                "_meta": {"title": "VAEDecode"},
            },
            "7": {
                "inputs": {"filename_prefix": "generated", "images": ["6", 0]},
                "class_type": "SaveImage",
                "_meta": {"title": "SaveImage"},
            },
        }
        logger.debug(
            "Built standard workflow: %s %dx%d steps=%d cfg=%.1f seed=%d",
            checkpoint, width, height, steps, cfg, seed,
        )
        return workflow

    # ------------------------------------------------------------------
    # Image upload
    # ------------------------------------------------------------------

    async def upload_image(
        self, image_bytes: bytes, filename: str = "input.png", overwrite: bool = True
    ) -> str:
        """
        Upload an image to ComfyUI's input directory via /upload/image.

        Args:
            image_bytes: Raw image bytes (PNG or JPEG).
            filename:    Filename to store under in ComfyUI's input folder.
            overwrite:   Whether to overwrite an existing file with the same name.

        Returns:
            The stored filename as reported by ComfyUI (use in LoadImage nodes).
        """
        import io as _io

        session = await self._get_session()
        url = f"{self.base_url}/upload/image"

        form_data = aiohttp.FormData()
        form_data.add_field(
            "image",
            _io.BytesIO(image_bytes),
            filename=filename,
            content_type="image/png",
        )
        form_data.add_field("type", "input")
        form_data.add_field("overwrite", "true" if overwrite else "false")

        logger.debug("Uploading image '%s' (%d bytes) to ComfyUI", filename, len(image_bytes))
        async with session.post(url, data=form_data, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise ComfyUIError(f"upload_image HTTP {resp.status}: {body[:200]}")
            data = await resp.json()

        stored_name: str = data.get("name", filename)
        logger.info("Uploaded image as '%s'", stored_name)
        return stored_name

    # ------------------------------------------------------------------
    # WebSocket progress
    # ------------------------------------------------------------------

    async def watch_progress(
        self,
        prompt_id: str,
        on_progress_cb: Optional[Callable[[dict], None]] = None,
    ) -> None:
        """
        Connect to ComfyUI's WebSocket and call *on_progress_cb* for each
        progress event related to *prompt_id*.

        Falls back to polling if the WebSocket connection fails.

        Args:
            prompt_id: The prompt to watch.
            on_progress_cb: Callable receiving progress event dicts.
        """
        ws_url = self.base_url.replace("http://", "ws://").replace("https://", "wss://")
        client_id = str(uuid.uuid4())
        ws_url = f"{ws_url}/ws?clientId={client_id}"

        logger.info("Watching progress via WebSocket for prompt_id=%s", prompt_id)
        try:
            session = await self._get_session()
            async with session.ws_connect(ws_url) as ws:
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        try:
                            data = json.loads(msg.data)
                        except json.JSONDecodeError:
                            continue

                        if data.get("type") == "progress" and on_progress_cb:
                            on_progress_cb(data.get("data", {}))

                        # Stop once our prompt finishes
                        if (
                            data.get("type") == "execution_complete"
                            and data.get("data", {}).get("prompt_id") == prompt_id
                        ):
                            logger.info("Execution complete for prompt_id=%s", prompt_id)
                            break

                    elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSE):
                        logger.warning("WebSocket closed/error: %s", msg)
                        break

        except Exception as exc:
            logger.warning("WebSocket watch failed (%s), falling back to polling", exc)
            await self.wait_for_completion(prompt_id)
