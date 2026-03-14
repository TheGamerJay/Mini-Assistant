# Lazy-load MiniAssistant so that importing any sub-package
# (e.g. mini_assistant.phase8.tool_registry) does NOT cascade into
# the heavy main.py dependency tree (brains, vector store, tools, etc.).
# Existing code that does `from mini_assistant import MiniAssistant`
# still works — Python calls __getattr__ on the first access.

__all__ = ["MiniAssistant"]


def __getattr__(name: str):
    if name == "MiniAssistant":
        from .main import MiniAssistant  # noqa: PLC0415
        return MiniAssistant
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
