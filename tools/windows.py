"""Window management via PyGetWindow (lazy). Supports 'close this window',
'go back to Chrome', etc. by exposing active/foreground window info."""
from __future__ import annotations

from safety.risk import RiskLevel
from tools.base import BaseTool, ToolResult


def _gw():
    import pygetwindow as gw  # type: ignore

    return gw


class _WindowTool(BaseTool):
    def invoke(self, arguments):
        try:
            _gw()
        except ImportError:
            return ToolResult.fail(self.name, "PYGETWINDOW_MISSING", "Install PyGetWindow.")
        return super().invoke(arguments)


class GetActiveWindow(_WindowTool):
    name = "get_active_window"
    description = "Return the title and size of the currently active (focused) window."
    risk = RiskLevel.SAFE
    parameters = {"type": "object", "properties": {}}

    def run(self) -> ToolResult:
        gw = _gw()
        active = gw.getActiveWindow()
        if not active:
            return ToolResult.fail(self.name, "NO_ACTIVE_WINDOW", "No active window found.")
        return ToolResult.ok(self.name, {
            "title": active.title,
            "left": active.left, "top": active.top,
            "width": active.width, "height": active.height,
            "is_maximized": bool(getattr(active, "isMaximized", False)),
        })


class ListWindows(_WindowTool):
    name = "list_windows"
    description = "List all open window titles."
    risk = RiskLevel.SAFE
    parameters = {"type": "object", "properties": {"filter": {"type": "string"}}}

    def run(self, filter: str = "") -> ToolResult:
        gw = _gw()
        titles = [w.title for w in gw.getAllWindows() if w.title]
        if filter:
            titles = [t for t in titles if filter.lower() in t.lower()]
        return ToolResult.ok(self.name, {"count": len(titles), "titles": titles[:50]})


class FocusWindow(_WindowTool):
    name = "focus_window"
    description = "Bring a window to the foreground by matching part of its title (e.g. 'Chrome')."
    risk = RiskLevel.SAFE
    parameters = {
        "type": "object",
        "properties": {"title": {"type": "string"}},
        "required": ["title"],
    }

    def run(self, title: str) -> ToolResult:
        gw = _gw()
        matches = [w for w in gw.getAllWindows() if w.title and title.lower() in w.title.lower()]
        if not matches:
            return ToolResult.fail(self.name, "WINDOW_NOT_FOUND", f"No window matching '{title}'.")
        win = matches[0]
        try:
            if getattr(win, "isMinimized", False):
                win.restore()
            win.activate()
        except Exception as exc:  # noqa: BLE001
            return ToolResult.fail(self.name, "FOCUS_FAILED", str(exc))
        return ToolResult.ok(self.name, {"title": win.title, "focused": True})
