"""Browser tools.

Basic operations (open_url, open_browser, web_search) use the OS default
browser and require nothing extra. Advanced DOM automation uses Playwright
lazily so it never blocks startup if not installed.
"""
from __future__ import annotations

import os
import subprocess
import webbrowser

from safety.risk import RiskLevel
from tools.base import BaseTool, ToolResult

_BROWSER_ENV = "JARVIS_DEFAULT_BROWSER"  # path/exe override from settings/memory
_KNOWN_URL_PREFIX = "https://"


def _default_browser() -> str | None:
    override = os.getenv(_BROWSER_ENV)
    if override:
        return override
    from tools.app_discovery import discover

    for candidate in ("chrome", "msedge", "firefox", "brave"):
        path = discover(candidate)
        if path:
            return path
    return None


def _ensure_scheme(url: str) -> str:
    url = url.strip()
    if url.startswith(("http://", "https://", "file://")):
        return url
    if "." in url and " " not in url:
        return _KNOWN_URL_PREFIX + url
    return url


class OpenBrowser(BaseTool):
    name = "open_browser"
    description = "Open the user's web browser (Chrome/Edge/Firefox) at an optional URL."
    risk = RiskLevel.SAFE
    parameters = {
        "type": "object",
        "properties": {"url": {"type": "string", "description": "Optional URL to open."}},
    }

    def run(self, url: str = "") -> ToolResult:
        browser = _default_browser()
        target = _ensure_scheme(url) if url else ""
        try:
            if browser:
                args = [target] if target else []
                subprocess.Popen([browser, *args], shell=False, close_fds=True)
            elif target:
                webbrowser.open(target)
            else:
                return ToolResult.fail(self.name, "NO_BROWSER", "No supported browser was found.")
        except Exception as exc:  # noqa: BLE001
            # fall back to the system default handler
            if target and webbrowser.open(target):
                return ToolResult.ok(self.name, {"browser": "system-default", "url": target})
            return ToolResult.fail(self.name, "OPEN_FAILED", str(exc))
        return ToolResult.ok(self.name, {"browser": browser or "system-default", "url": target or None})


class OpenUrl(BaseTool):
    name = "open_url"
    description = "Open a specific URL in the user's browser."
    risk = RiskLevel.SAFE
    parameters = {
        "type": "object",
        "properties": {"url": {"type": "string", "description": "Full URL or domain (scheme optional)."}},
        "required": ["url"],
    }

    def run(self, url: str) -> ToolResult:
        target = _ensure_scheme(url)
        browser = _default_browser()
        try:
            if browser:
                subprocess.Popen([browser, target], shell=False, close_fds=True)
                return ToolResult.ok(self.name, {"browser": browser, "url": target})
            if webbrowser.open(target):
                return ToolResult.ok(self.name, {"browser": "system-default", "url": target})
        except Exception as exc:  # noqa: BLE001
            return ToolResult.fail(self.name, "OPEN_FAILED", str(exc))
        return ToolResult.fail(self.name, "NO_BROWSER", "Could not open a browser.")


class ReadPage(BaseTool):
    name = "read_page"
    description = "Fetch a page's visible text using Playwright (headless). Requires 'playwright install'."
    risk = RiskLevel.CAUTION
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "max_chars": {"type": "integer", "description": "Max characters of text to return (default 5000)."},
        },
        "required": ["url"],
    }

    def run(self, url: str, max_chars: int = 5000) -> ToolResult:
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
        except ImportError:
            return ToolResult.fail(
                self.name, "PLAYWRIGHT_MISSING",
                "Playwright is not installed. Run: pip install playwright && playwright install",
            )
        target = _ensure_scheme(url)
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(target, timeout=30000, wait_until="domcontentloaded")
                title = page.title()
                text = page.inner_text("body")[:max_chars]
                browser.close()
        except Exception as exc:  # noqa: BLE001
            return ToolResult.fail(self.name, "READ_FAILED", str(exc))
        return ToolResult.ok(self.name, {"url": target, "title": title, "text": text})
