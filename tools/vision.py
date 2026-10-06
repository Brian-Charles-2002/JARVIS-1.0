"""Gemini vision: capture the screen and have Gemini analyze it.

Only invoked when the user explicitly asks ("what's on my screen?", "read this
error"). Never runs continuously - privacy matters. Requires a Gemini client
capable of multimodal input, injected at registry build time.
"""
from __future__ import annotations

import time
from pathlib import Path

from config.settings import SCREENSHOT_DIR
from safety.risk import RiskLevel
from tools.base import BaseTool, ToolResult


class AnalyzeScreen(BaseTool):
    name = "analyze_screen"
    description = (
        "Take a screenshot and ask Gemini to interpret it (describe the screen, read an "
        "error, find a button). Use only when visual inspection is genuinely required."
    )
    risk = RiskLevel.SAFE
    parameters = {
        "type": "object",
        "properties": {
            "instruction": {"type": "string", "description": "What to look for or answer about the screen."}
        },
        "required": ["instruction"],
    }

    def run(self, instruction: str) -> ToolResult:
        client = getattr(self, "ai_client", None)
        if client is None:
            return ToolResult.fail(self.name, "NO_AI_CLIENT", "Vision is not wired to a Gemini client.")
        try:
            import pyautogui  # type: ignore
        except ImportError:
            return ToolResult.fail(self.name, "PYAUTOGUI_MISSING", "Install pyautogui to capture the screen.")

        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = SCREENSHOT_DIR / f"vision_{time.strftime('%Y%m%d_%H%M%S')}.png"
        try:
            pyautogui.screenshot(str(out_path))
        except Exception as exc:  # noqa: BLE001
            return ToolResult.fail(self.name, "SCREENSHOT_FAILED", str(exc))

        try:
            analysis = client.analyze_image(out_path, instruction or "Describe what is on this screen.")
        except Exception as exc:  # noqa: BLE001
            return ToolResult.fail(self.name, "VISION_ERROR", str(exc))

        return ToolResult.ok(self.name, {"screenshot": str(out_path), "analysis": analysis})
