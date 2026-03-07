"""
computer.py – Computer Control Tool
─────────────────────────────────────
Controls the desktop using PyAutoGUI.
Captures screenshots for vision-assisted automation.
All actions include a safety delay to prevent runaway automation.
"""

import base64
import logging
import time
from io import BytesIO
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_SAFETY_DELAY = 0.3   # seconds between actions


def _safe_import_pyautogui():
    try:
        import pyautogui
        pyautogui.FAILSAFE = True      # move mouse to corner to abort
        pyautogui.PAUSE    = _SAFETY_DELAY
        return pyautogui
    except ImportError:
        raise ImportError(
            "pyautogui is not installed. Run: pip install pyautogui pillow"
        )


# ─── Screenshot ───────────────────────────────────────────────────────────────

def take_screenshot(region: Optional[tuple] = None) -> dict:
    """
    Capture the screen and return a base64-encoded PNG.

    Args:
        region: Optional (left, top, width, height) tuple to capture a sub-region.

    Returns:
        dict with keys: success, image_b64, width, height
    """
    try:
        pag = _safe_import_pyautogui()
        screenshot = pag.screenshot(region=region)
        buf = BytesIO()
        screenshot.save(buf, format="PNG")
        img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return {
            "success":   True,
            "image_b64": img_b64,
            "width":     screenshot.width,
            "height":    screenshot.height,
        }
    except Exception as exc:
        logger.error("Screenshot failed: %s", exc)
        return {"success": False, "error": str(exc)}


# ─── Mouse ────────────────────────────────────────────────────────────────────

def click(x: int, y: int, button: str = "left", clicks: int = 1) -> dict:
    """Click at screen coordinates."""
    try:
        pag = _safe_import_pyautogui()
        pag.click(x, y, button=button, clicks=clicks)
        return {"success": True, "action": "click", "x": x, "y": y, "button": button}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def move_to(x: int, y: int, duration: float = 0.3) -> dict:
    """Move the mouse cursor to coordinates."""
    try:
        pag = _safe_import_pyautogui()
        pag.moveTo(x, y, duration=duration)
        return {"success": True, "action": "move", "x": x, "y": y}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def scroll(x: int, y: int, amount: int = 3) -> dict:
    """Scroll at coordinates. Positive = up, negative = down."""
    try:
        pag = _safe_import_pyautogui()
        pag.scroll(amount, x=x, y=y)
        return {"success": True, "action": "scroll", "x": x, "y": y, "amount": amount}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


# ─── Keyboard ─────────────────────────────────────────────────────────────────

def type_text(text: str, interval: float = 0.05) -> dict:
    """Type a string at the current cursor position."""
    try:
        pag = _safe_import_pyautogui()
        pag.typewrite(text, interval=interval)
        return {"success": True, "action": "type", "text": text}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def press_key(key: str) -> dict:
    """Press a single key or key combination (e.g. 'enter', 'ctrl+c')."""
    try:
        pag = _safe_import_pyautogui()
        keys = key.lower().split("+")
        if len(keys) > 1:
            pag.hotkey(*keys)
        else:
            pag.press(keys[0])
        return {"success": True, "action": "keypress", "key": key}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


# ─── App launcher ─────────────────────────────────────────────────────────────

def open_app(app_name: str) -> dict:
    """
    Open an application by name. Uses the OS's default launcher.
    Windows: start <app>, Linux: xdg-open / which, macOS: open -a
    """
    import subprocess, sys
    try:
        if sys.platform == "win32":
            subprocess.Popen(["start", app_name], shell=True)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-a", app_name])
        else:
            subprocess.Popen(["xdg-open", app_name])
        return {"success": True, "action": "open_app", "app": app_name}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


# ─── Locate on screen ─────────────────────────────────────────────────────────

def find_on_screen(image_path: str, confidence: float = 0.8) -> dict:
    """
    Locate an image on screen and return its center coordinates.
    Requires pillow and a Retina/HiDPI-aware setup.
    """
    try:
        pag = _safe_import_pyautogui()
        location = pag.locateOnScreen(image_path, confidence=confidence)
        if location:
            center = pag.center(location)
            return {"success": True, "found": True, "x": center.x, "y": center.y}
        return {"success": True, "found": False}
    except Exception as exc:
        return {"success": False, "error": str(exc)}
