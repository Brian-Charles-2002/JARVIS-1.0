"""Short-term (session) memory.

Tracks structured session state so references like 'it', 'that folder', 'there',
'the browser' can be resolved without replaying the entire chat to Gemini.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from tools.base import ToolResult

_MAX_RESULTS = 15


@dataclass
class ShortTermMemory:
    current_application: str | None = None
    active_browser: str | None = None
    last_created_file: str | None = None
    last_created_folder: str | None = None
    last_opened_file: str | None = None
    last_url: str | None = None
    last_search_query: str | None = None
    current_task: str | None = None
    last_assistant_text: str | None = None
    recent_entities: deque = field(default_factory=lambda: deque(maxlen=20))
    recent_tool_results: deque = field(default_factory=lambda: deque(maxlen=_MAX_RESULTS))

    def add_entity(self, entity: str) -> None:
        entity = (entity or "").strip()
        if entity and (not self.recent_entities or self.recent_entities[-1] != entity):
            self.recent_entities.append(entity)

    def note_result(self, tool: str, arguments: dict[str, Any], result: ToolResult) -> None:
        """Update session state from a tool call/result."""
        if not result.success:
            self.recent_tool_results.append({"tool": tool, "success": False})
            return
        payload = result.result or {}
        path = payload.get("path") or payload.get("from") or payload.get("to")
        url = payload.get("url")
        self.recent_tool_results.append({
            "tool": tool,
            "success": True,
            "summary": _summarize(tool, payload),
        })

        if tool == "create_folder" and path:
            self.last_created_folder = path
            self.add_entity(path)
        elif tool == "create_file" and path:
            self.last_created_file = path
            self.add_entity(path)
        elif tool in ("write_file", "append_file") and path:
            self.last_created_file = self.last_created_file or path
        elif tool in ("open_file", "read_file") and path:
            self.last_opened_file = path
        elif tool == "move_file" and payload.get("to"):
            if _looks_like_dir(payload["to"]):
                self.last_created_folder = payload["to"]
            else:
                self.last_created_file = payload["to"]
        elif tool == "open_application":
            self.current_application = payload.get("application")
            self.add_entity(str(self.current_application))
        elif tool in ("open_browser", "open_url"):
            self.active_browser = payload.get("browser") or self.active_browser
            if url:
                self.last_url = url
        elif tool == "web_search":
            query = payload.get("query") or arguments.get("query")
            if query:
                self.last_search_query = query
                self.add_entity(query)

        # Any browser-automation tool also feeds the current page reference.
        if tool.startswith("browser_") and payload.get("url"):
            self.active_browser = self.active_browser or "playwright"
            self.last_url = payload["url"]
            self.add_entity(payload.get("title") or payload["url"])

    def to_context_dict(self) -> dict[str, Any]:
        """Serializable snapshot injected into the prompt as structured context."""
        data = {
            "current_application": self.current_application,
            "active_browser": self.active_browser,
            "last_created_file": self.last_created_file,
            "last_created_folder": self.last_created_folder,
            "last_opened_file": self.last_opened_file,
            "last_url": self.last_url,
            "last_search_query": self.last_search_query,
            "current_task": self.current_task,
            "recent_entities": list(self.recent_entities)[-8:],
            "recent_tool_results": list(self.recent_tool_results)[-8:],
        }
        return {k: v for k, v in data.items() if v}


def _looks_like_dir(path: str) -> bool:
    return "." not in path.split("\\")[-1].split("/")[-1]


def _summarize(tool: str, payload: dict[str, Any]) -> str:
    for key in ("path", "url", "to", "application", "query", "title"):
        if payload.get(key):
            return f"{tool}: {payload[key]}"
    return tool
