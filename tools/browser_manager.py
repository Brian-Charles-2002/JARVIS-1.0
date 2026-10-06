"""Persistent Playwright browser session shared across tool calls.

One browser/context/page lives for the whole session so multi-turn browser work
("open YouTube" -> "search ..." -> "open the first one") reuses the same page
instead of launching a fresh browser each time. A single module-level manager is
reused; heavy Playwright imports are lazy so the assistant runs without it.
"""
from __future__ import annotations

import os
from typing import Any

_manager: "BrowserManager | None" = None


def get_manager(headless: bool | None = None) -> "BrowserManager":
    global _manager
    if _manager is None:
        if headless is None:
            headless = os.getenv("BROWSER_HEADLESS", "false").strip().lower() in {"1", "true", "yes"}
        _manager = BrowserManager(headless=headless)
    return _manager


def shutdown_manager() -> None:
    """Close the browser if a session was ever started (safe if not)."""
    global _manager
    if _manager is not None:
        _manager.close()
        _manager = None


def _ensure_scheme(url: str) -> str:
    url = (url or "").strip()
    if url.startswith(("http://", "https://", "file://")):
        return url
    if "." in url and " " not in url:
        return "https://" + url
    return "https://" + url


class BrowserManager:
    def __init__(self, headless: bool = False) -> None:
        self.headless = headless
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None

    @property
    def active(self) -> bool:
        return self._page is not None

    def ensure(self) -> Any:
        """Start (or reuse) the browser and return the active page."""
        if self._page is not None:
            return self._page
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is not installed. Run: pip install playwright && playwright install"
            ) from exc

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless)
        self._context = self._browser.new_context()
        self._page = self._context.new_page()
        self._page.set_default_timeout(30000)
        return self._page

    def state(self) -> dict[str, Any]:
        if self._page is None:
            return {"active": False}
        return {
            "active": True,
            "url": self._page.url,
            "title": self._page.title(),
            "tabs": len(self._context.pages) if self._context else 1,
        }

    def navigate(self, url: str) -> dict[str, Any]:
        page = self.ensure()
        target = _ensure_scheme(url)
        page.goto(target, wait_until="domcontentloaded")
        page.wait_for_timeout(500)
        return {"url": page.url, "title": page.title()}

    def get_text(self, max_chars: int = 6000) -> dict[str, Any]:
        page = self.ensure()
        try:
            text = page.inner_text("body")
        except Exception:  # noqa: BLE001
            text = ""
        return {"url": page.url, "title": page.title(), "text": text[:max_chars]}

    def get_links(self, max_links: int = 25) -> dict[str, Any]:
        page = self.ensure()
        anchors = page.query_selector_all("a[href]")
        links: list[dict[str, str]] = []
        seen = set()
        for a in anchors:
            href = a.get_attribute("href") or ""
            if not href or href.startswith("#") or href in seen:
                continue
            try:
                text = (a.inner_text() or "").strip().replace("\n", " ")
            except Exception:  # noqa: BLE001
                text = ""
            if not text:
                continue
            seen.add(href)
            links.append({"text": text[:120], "url": self._abs(href)})
            if len(links) >= max_links:
                break
        return {"url": page.url, "title": page.title(), "links": links}

    def _abs(self, href: str) -> str:
        page = self.ensure()
        try:
            return page.evaluate("u => new URL(u, document.baseURI).href", href)
        except Exception:  # noqa: BLE001
            return href

    def click(self, target: str) -> dict[str, Any]:
        page = self.ensure()
        # try a visible-text click first (most natural), then a CSS selector.
        try:
            page.get_by_text(target, exact=False).first.click(timeout=8000)
            method = "text"
        except Exception:  # noqa: BLE001
            page.click(target, timeout=8000)
            method = "selector"
        page.wait_for_timeout(500)
        return {"clicked": target, "method": method, "url": page.url, "title": page.title()}

    def type_text(self, selector: str, text: str, submit: bool = False) -> dict[str, Any]:
        page = self.ensure()
        page.fill(selector, text, timeout=8000)
        if submit:
            page.press(selector, "Enter")
            page.wait_for_timeout(800)
        return {"selector": selector, "typed": len(text), "submitted": submit, "url": page.url}

    def search(self, query: str) -> dict[str, Any]:
        return self.navigate("https://duckduckgo.com/?q=" + _quote(query))

    def scroll(self, direction: str, amount: int = 500) -> dict[str, Any]:
        page = self.ensure()
        delta = amount if direction.lower().startswith("up") else -amount
        page.mouse.wheel(0, delta)
        page.wait_for_timeout(200)
        return {"direction": direction, "delta": delta}

    def close(self) -> None:
        for closer in (
            lambda: self._context.close() if self._context else None,
            lambda: self._browser.close() if self._browser else None,
            lambda: self._pw.stop() if self._pw else None,
        ):
            try:
                closer()
            except Exception:  # noqa: BLE001
                pass
        self._page = self._context = self._browser = self._pw = None


def _quote(text: str) -> str:
    from urllib.parse import quote

    return quote(text)
