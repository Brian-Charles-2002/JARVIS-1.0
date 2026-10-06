"""Keyboard and mouse automation via PyAutoGUI (imported lazily).

Prefer native APIs / DOM automation over these for reliability; PyAutoGUI acts
on whatever window currently has focus.
"""
from __future__ import annotations

from safety.risk import RiskLevel
from tools.base import BaseTool, ToolResult


def _gui():
    """Return a configured pyautogui module or raise ImportError."""
    import pyautogui  # type: ignore

    pyautogui.FAILSAFE = True  # move mouse to top-left corner to abort
    return pyautogui


class _GuiTool(BaseTool):
    def invoke(self, arguments):  # noqa: D401 - shared gui import guard
        try:
            _gui()
        except ImportError:
            return ToolResult.fail(
                self.name, "PYAUTOGUI_MISSING",
                "PyAutoGUI is not installed. Run: pip install pyautogui",
            )
        return super().invoke(arguments)


class TypeText(_GuiTool):
    name = "type_text"
    description = "Type text into the currently focused window/application."
    risk = RiskLevel.CAUTION
    parameters = {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "interval_seconds": {"type": "number", "description": "Delay between keystrokes (default 0.02)."},
        },
        "required": ["text"],
    }

    def run(self, text: str, interval_seconds: float = 0.02) -> ToolResult:
        py = _gui()
        py.typewrite(text, interval=interval_seconds) if text.isascii() else py.write(text, interval=interval_seconds)
        return ToolResult.ok(self.name, {"typed_chars": len(text)})


class PressKey(_GuiTool):
    name = "press_key"
    description = "Press a single key (e.g. 'enter', 'tab', 'escape', 'f5')."
    risk = RiskLevel.CAUTION
    parameters = {
        "type": "object",
        "properties": {"key": {"type": "string"}},
        "required": ["key"],
    }

    def run(self, key: str) -> ToolResult:
        py = _gui()
        py.press(key.lower())
        return ToolResult.ok(self.name, {"key": key})


class Hotkey(_GuiTool):
    name = "hotkey"
    description = "Press a key combination, e.g. keys=['ctrl','shift','esc'] for Task Manager."
    risk = RiskLevel.CAUTION
    parameters = {
        "type": "object",
        "properties": {"keys": {"type": "array", "items": {"type": "string"}}},
        "required": ["keys"],
    }

    def run(self, keys: list[str]) -> ToolResult:
        py = _gui()
        py.hotkey(*[k.lower() for k in keys])
        return ToolResult.ok(self.name, {"keys": keys})


class ClickMouse(_GuiTool):
    name = "click_mouse"
    description = "Click the mouse. If x/y are omitted, clicks at the current pointer position."
    risk = RiskLevel.CAUTION
    parameters = {
        "type": "object",
        "properties": {
            "x": {"type": "integer", "description": "Screen X (must be determined dynamically, not guessed)."},
            "y": {"type": "integer"},
            "button": {"type": "string", "description": "left | right | middle (default left)."},
            "clicks": {"type": "integer", "description": "Number of clicks (2 = double-click)."},
        },
    }

    def run(self, x: int | None = None, y: int | None = None,
            button: str = "left", clicks: int = 1) -> ToolResult:
        py = _gui()
        if x is None or y is None:
            pos = py.position()
            x, y = int(pos.x), int(pos.y)
        py.click(x=x, y=y, button=button, clicks=clicks)
        return ToolResult.ok(self.name, {"x": x, "y": y, "button": button, "clicks": clicks})


class DoubleClick(ClickMouse):
    name = "double_click"
    description = "Double-click the mouse at optional x/y."

    def run(self, x: int | None = None, y: int | None = None,
            button: str = "left", clicks: int = 1) -> ToolResult:  # type: ignore[override]
        return super().run(x=x, y=y, button=button, clicks=2)


class RightClick(ClickMouse):
    name = "right_click"
    description = "Right-click the mouse at optional x/y."

    def run(self, x: int | None = None, y: int | None = None,
            button: str = "left", clicks: int = 1) -> ToolResult:  # type: ignore[override]
        return super().run(x=x, y=y, button="right", clicks=1)


class MoveMouse(_GuiTool):
    name = "move_mouse"
    description = "Move the mouse pointer to x/y."
    risk = RiskLevel.SAFE
    parameters = {
        "type": "object",
        "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}},
        "required": ["x", "y"],
    }

    def run(self, x: int, y: int) -> ToolResult:
        py = _gui()
        py.moveTo(x, y)
        return ToolResult.ok(self.name, {"x": x, "y": y})


class Scroll(_GuiTool):
    name = "scroll"
    description = "Scroll the mouse wheel. Positive amount scrolls up, negative scrolls down."
    risk = RiskLevel.SAFE
    parameters = {
        "type": "object",
        "properties": {"amount": {"type": "integer", "description": "Scroll units (default 3)."}},
    }

    def run(self, amount: int = 3) -> ToolResult:
        py = _gui()
        py.scroll(amount)
        return ToolResult.ok(self.name, {"amount": amount})
