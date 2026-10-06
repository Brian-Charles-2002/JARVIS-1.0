"""Central tool registry decoupling Gemini from concrete implementations."""
from __future__ import annotations

from typing import Any

from core.exceptions import ToolError
from safety.risk import RiskLevel
from tools.base import BaseTool, ToolCall, ToolResult


class ToolRegistry:
    """Holds all available tools and dispatches calls by name."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        if not tool.name:
            raise ToolError("INVALID_TOOL", "Tool must declare a non-empty name")
        self._tools[tool.name] = tool

    def register_all(self, tools: list[BaseTool]) -> None:
        for tool in tools:
            self.register(tool)

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    @property
    def names(self) -> list[str]:
        return list(self._tools)

    def risk_of(self, name: str, arguments: dict[str, Any] | None = None) -> RiskLevel:
        tool = self._tools.get(name)
        if not tool:
            return RiskLevel.SENSITIVE
        return tool.risk_for(arguments or {})

    def schemas(self) -> list[dict[str, Any]]:
        """Function declarations suitable for the Gemini tool adapter."""
        return [tool.schema() for tool in self._tools.values()]

    def call(self, tool_call: ToolCall) -> ToolResult:
        tool = self._tools.get(tool_call.name)
        if tool is None:
            return ToolResult.fail(tool_call.name, "UNKNOWN_TOOL",
                                   f"No tool named '{tool_call.name}' is registered.")
        return tool.invoke(tool_call.arguments)
