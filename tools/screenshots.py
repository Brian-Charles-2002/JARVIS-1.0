"""Screenshot capture into a controlled directory.

Returns the saved path and metadata. Vision analysis is a separate concern
(see ai/gemini_client.analyze_image) and only runs when explicitly requested.
"""
from __future__ import annotations

import time
from pathlib import Path

from config.settings import SCREENSHOT_DIR
from safety.risk import RiskLevel
from tools.base import BaseTool, ToolResult


class TakeScreenshot(BaseTool):
    name = "take_screenshot"
    description = "Capture the current screen to an image file and return its path. Only use when visual inspection is genuinely required."
    risk = RiskLevel.SAFE
    parameters = {"type": "object", "properties": {"region": {
        "type": "string", "description": "Optional 'x,y,width,height' region."}}}

    def run(self, region: str = "") -> ToolResult:
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = SCREENSHOT_DIR / f"screenshot_{time.strftime('%Y%m%d_%H%M%S')}.png"
        try:
            import pyautogui  # type: ignore
        except ImportError:
            return ToolResult.fail(self.name, "PYAUTOGUI_MISSING", "Install pyautogui to take screenshots.")
        try:
            box = None
            if region:
                parts = [int(p.strip()) for p in region.split(",")]
                if len(parts) == 4:
                    box = tuple(parts)  # type: ignore[assignment]
            pyautogui.screenshot(str(out_path), region=box)  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001
            return ToolResult.fail(self.name, "SCREENSHOT_FAILED", str(exc))
        return ToolResult.ok(self.name, {
            "path": str(out_path),
            "size_bytes": Path(out_path).stat().st_size,
        })
