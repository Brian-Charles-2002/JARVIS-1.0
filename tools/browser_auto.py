"""DOM browser-automation tools driven by the shared BrowserManager.

These give Gemini reliable page interaction (navigate/read/click/type) instead
of guessed screen coordinates. Playwright is imported lazily inside the manager,
so each tool degrades to a structured error if it isn't installed.
"""
from __future__ import annotations

from typing import Any

from safety.risk import RiskLevel
from tools.base import BaseTool, ToolResult
from tools.browser_manager import get_manager


class _BrowserTool(BaseTool):
    def _call(self, fn, *args, **kwargs) -> ToolResult:
        try:
            data = fn(*args, **kwargs)
        except RuntimeError as exc:  # Playwright missing
            return ToolResult.fail(self.name, "PLAYWRIGHT_MISSING", str(exc))
        except Exception as exc:  # noqa: BLE001 - page/DOM error
            return ToolResult.fail(self.name, "BROWSER_ERROR", f"{type(exc).__name__}: {exc}")
        return ToolResult.ok(self.name, data)

    def manager(self):
        headless = getattr(self.settings, "browser_headless", None)
        return get_manager(headless=headless)


class BrowserNavigate(_BrowserTool):
    name = "browser_navigate"
    description = "Open a URL in JARVIS's controlled browser session and return the page title/URL."
    risk = RiskLevel.CAUTION
    parameters = {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}

    def run(self, url: str) -> ToolResult:
        return self._call(self.manager().navigate, url)


class BrowserGetText(_BrowserTool):
    name = "browser_get_text"
    description = "Read the visible text of the current page in the browser session."
    risk = RiskLevel.SAFE
    parameters = {"type": "object", "properties": {"max_chars": {"type": "integer"}}}

    def run(self, max_chars: int = 6000) -> ToolResult:
        return self._call(self.manager().get_text, max_chars)


class BrowserGetLinks(_BrowserTool):
    name = "browser_get_links"
    description = "List clickable links (text + absolute url) on the current page, e.g. search results, so you can pick 'the first relevant one'."
    risk = RiskLevel.SAFE
    parameters = {"type": "object", "properties": {"max_links": {"type": "integer"}}}

    def run(self, max_links: int = 25) -> ToolResult:
        return self._call(self.manager().get_links, max_links)


class BrowserSearch(_BrowserTool):
    name = "browser_search"
    description = "Search the web in the browser session (DuckDuckGo) and return the results page."
    risk = RiskLevel.CAUTION
    parameters = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}

    def run(self, query: str) -> ToolResult:
        return self._call(self.manager().search, query)


class BrowserClick(_BrowserTool):
    name = "browser_click"
    description = "Click an element on the current page by its visible text (preferred) or a CSS selector."
    risk = RiskLevel.CAUTION
    parameters = {"type": "object", "properties": {"target": {"type": "string"}}, "required": ["target"]}

    def run(self, target: str) -> ToolResult:
        return self._call(self.manager().click, target)


class BrowserType(_BrowserTool):
    name = "browser_type"
    description = "Type text into a field (CSS selector). If submit is true it presses Enter - set submit true only with user awareness."
    risk = RiskLevel.CAUTION
    parameters = {
        "type": "object",
        "properties": {
            "selector": {"type": "string"},
            "text": {"type": "string"},
            "submit": {"type": "boolean"},
        },
        "required": ["selector", "text"],
    }

    def risk_for(self, arguments: dict[str, Any]) -> RiskLevel:
        return RiskLevel.SENSITIVE if arguments.get("submit") else self.risk

    def run(self, selector: str, text: str, submit: bool = False) -> ToolResult:
        return self._call(self.manager().type_text, selector, text, submit)


class BrowserScroll(_BrowserTool):
    name = "browser_scroll"
    description = "Scroll the current page up or down."
    risk = RiskLevel.SAFE
    parameters = {
        "type": "object",
        "properties": {"direction": {"type": "string", "description": "up | down"}, "amount": {"type": "integer"}},
        "required": ["direction"],
    }

    def run(self, direction: str, amount: int = 500) -> ToolResult:
        return self._call(self.manager().scroll, direction, amount)


class BrowserState(_BrowserTool):
    name = "browser_state"
    description = "Report whether JARVIS's browser is open and its current URL/title/tab count."
    risk = RiskLevel.SAFE
    parameters = {"type": "object", "properties": {}}

    def run(self) -> ToolResult:
        return self._call(self.manager().state)


class BrowserClose(_BrowserTool):
    name = "browser_close"
    description = "Close JARVIS's controlled browser session."
    risk = RiskLevel.CAUTION
    parameters = {"type": "object", "properties": {}}

    def run(self) -> ToolResult:
        return self._call(self.manager().close)


BROWSER_TOOLS = [
    BrowserNavigate, BrowserGetText, BrowserGetLinks, BrowserSearch,
    BrowserClick, BrowserType, BrowserScroll, BrowserState, BrowserClose,
]
