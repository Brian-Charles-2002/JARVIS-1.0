"""Clipboard tools (pyperclip, lazy). Never auto-uploaded to Gemini."""
from __future__ import annotations

from safety.risk import RiskLevel
from tools.base import BaseTool, ToolResult


def _clip():
    import pyperclip  # type: ignore

    return pyperclip


class GetClipboard(BaseTool):
    name = "get_clipboard"
    description = "Read the current text on the clipboard. Contents may be sensitive - only use when required."
    risk = RiskLevel.SAFE
    parameters = {"type": "object", "properties": {}}

    def run(self) -> ToolResult:
        try:
            text = _clip().paste()
        except ImportError:
            return ToolResult.fail(self.name, "PYPERCLIP_MISSING", "Install pyperclip.")
        except Exception as exc:  # noqa: BLE001
            return ToolResult.fail(self.name, "CLIPBOARD_ERROR", str(exc))
        return ToolResult.ok(self.name, {"text": text or ""})


class SetClipboard(BaseTool):
    name = "set_clipboard"
    description = "Place text onto the clipboard."
    risk = RiskLevel.CAUTION
    parameters = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }

    def run(self, text: str) -> ToolResult:
        try:
            _clip().copy(text)
        except ImportError:
            return ToolResult.fail(self.name, "PYPERCLIP_MISSING", "Install pyperclip.")
        except Exception as exc:  # noqa: BLE001
            return ToolResult.fail(self.name, "CLIPBOARD_ERROR", str(exc))
        return ToolResult.ok(self.name, {"copied_chars": len(text)})
