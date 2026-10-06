"""Keyless web search abstraction returning structured results."""
from __future__ import annotations

from safety.risk import RiskLevel
from tools.base import BaseTool, ToolResult


class WebSearch(BaseTool):
    name = "web_search"
    description = (
        "Search the live web for current information and return structured results "
        "(title, url, snippet). Use this whenever the user asks for recent/current facts."
    )
    risk = RiskLevel.SAFE
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query."},
            "max_results": {"type": "integer", "description": "Number of results (default 6)."},
        },
        "required": ["query"],
    }

    def run(self, query: str, max_results: int = 6) -> ToolResult:
        try:
            from duckduckgo_search import DDGS  # type: ignore
        except ImportError:
            return ToolResult.fail(
                self.name, "SEARCH_BACKEND_MISSING",
                "Install a search backend: pip install duckduckgo-search",
            )
        try:
            with DDGS() as ddgs:
                raw = list(ddgs.text(query, max_results=max_results))
            results = [
                {
                    "title": item.get("title"),
                    "url": item.get("href") or item.get("url"),
                    "snippet": item.get("body"),
                }
                for item in raw
            ]
        except Exception as exc:  # noqa: BLE001
            return ToolResult.fail(self.name, "SEARCH_ERROR", str(exc))
        return ToolResult.ok(self.name, {"query": query, "results": results})
