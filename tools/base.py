"""Tool foundation: structured results, calls, and the BaseTool contract."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable

from safety.risk import RiskLevel


@dataclass
class ToolResult:
    """Uniform structured result returned by every tool.

    Serialized form (fed back to Gemini)::

        {"success": bool, "tool": str, "result": Any, "error": {..}|None}
    """

    success: bool
    tool: str
    result: Any = None
    error: dict[str, str] | None = None
    elapsed_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "success": self.success,
            "tool": self.tool,
            "result": self.result,
            "error": self.error,
        }
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload

    @classmethod
    def ok(cls, tool: str, result: Any = None, **metadata: Any) -> "ToolResult":
        return cls(success=True, tool=tool, result=result, metadata=metadata)

    @classmethod
    def fail(cls, tool: str, code: str, message: str) -> "ToolResult":
        return cls(success=False, tool=tool, result=None, error={"type": code, "message": message})


@dataclass
class ToolCall:
    """A single tool invocation requested by the model."""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


# A tool handler is any callable taking keyword arguments and returning ToolResult.
Handler = Callable[..., ToolResult]

_TYPE_MAP: dict[str, type | tuple[type, ...]] = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}


class BaseTool(ABC):
    """Base class every computer capability must implement.

    Subclasses declare ``name``, ``description``, ``risk`` and a JSON-schema
    ``parameters`` block, then implement :meth:`run`. The registry exposes the
    schema to Gemini; :meth:`invoke` validates arguments and wraps execution so
    a single failure never crashes the assistant.
    """

    name: str = ""
    description: str = ""
    risk: RiskLevel = RiskLevel.SAFE
    parameters: dict[str, Any] = {"type": "object", "properties": {}}

    def __init__(self, settings: Any | None = None) -> None:
        self.settings = settings

    # --- schema helpers -----------------------------------------------------
    @property
    def required(self) -> list[str]:
        return self.parameters.get("required", [])

    def risk_for(self, arguments: dict[str, Any]) -> RiskLevel:
        """Risk level for a specific call. Defaults to the tool's static risk.

        Tools like the terminal override this to classify the actual command.
        """
        return self.risk

    def validate(self, arguments: dict[str, Any]) -> None:
        """Raise ``ValueError`` for missing or wrongly-typed arguments."""
        props = self.parameters.get("properties", {})
        for req in self.required:
            if req not in arguments or arguments[req] in (None, ""):
                raise ValueError(f"Missing required argument '{req}'")
        for key, value in arguments.items():
            if key not in props:
                continue
            expected = props[key].get("type")
            py_type = _TYPE_MAP.get(expected) if expected else None
            if py_type and value is not None and not isinstance(value, py_type):
                # bool is a subclass of int; reject bool where int expected
                if expected == "integer" and isinstance(value, bool):
                    raise ValueError(f"Argument '{key}' must be {expected}")
                raise ValueError(
                    f"Argument '{key}' must be {expected}, got {type(value).__name__}"
                )

    @abstractmethod
    def run(self, **arguments: Any) -> ToolResult:
        """Perform the action. Must return a structured ToolResult."""

    def invoke(self, arguments: dict[str, Any]) -> ToolResult:
        """Validate then execute, converting exceptions into failure results."""
        started = time.perf_counter()
        try:
            self.validate(arguments)
        except ValueError as exc:
            return ToolResult.fail(self.name, "INVALID_ARGUMENTS", str(exc))
        try:
            result = self.run(**arguments)
        except NotImplementedError as exc:
            return ToolResult.fail(self.name, "NOT_IMPLEMENTED", str(exc))
        except Exception as exc:  # noqa: BLE001 - boundary: never crash the loop
            return ToolResult.fail(self.name, "EXECUTION_ERROR", f"{type(exc).__name__}: {exc}")
        result.elapsed_ms = (time.perf_counter() - started) * 1000
        result.tool = self.name
        return result

    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }
