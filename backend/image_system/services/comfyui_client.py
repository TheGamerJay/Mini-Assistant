"""comfyui_client.py — ComfyUI removed. Image generation uses OpenAI DALL-E."""


class ComfyUIError(Exception):
    pass


class ComfyUIClient:
    """Stub — ComfyUI removed. Use DalleClient for image generation."""

    def __init__(self, *a, **kw):
        pass

    async def generate(self, *a, **kw):
        raise NotImplementedError("ComfyUI removed — use DalleClient")

    def build_standard_workflow(self, *a, **kw):
        return {}

    def inject_params(self, w, *a, **kw):
        return w

    async def upload_image(self, *a, **kw):
        return ""

    async def queue_status(self):
        return {}

    async def interrupt(self):
        pass

    async def load_workflow(self, *a, **kw):
        return {}
