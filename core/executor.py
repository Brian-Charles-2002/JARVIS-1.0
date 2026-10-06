"""Tool executor: the safe execution boundary.

Assumes the permission/confirmation gate has already approved the call. Checks
the cancellation token, runs the tool, and records the outcome into session
memory. A tool failure returns a structured result and never raises.
"""
from __future__ import annotations

from config.settings import Settings
from core.events import CancellationToken
from core.logging_setup import get_logger
from memory.short_term import ShortTermMemory
from tools.base import ToolCall, ToolResult
from tools.registry import ToolRegistry

logger = get_logger("core.executor")


class ToolExecutor:
    def __init__(self, registry: ToolRegistry, short_term: ShortTermMemory,
                 settings: Settings) -> None:
        self.registry = registry
        self.short_term = short_term
        self.settings = settings

    def execute(self, call: ToolCall, token: CancellationToken | None = None) -> ToolResult:
        if token is not None:
            token.check()
        logger.info("Executing tool=%s args=%s", call.name, _redact(call.arguments))
        result = self.registry.call(call)
        self.short_term.note_result(call.name, call.arguments, result)
        logger.info("Tool %s -> success=%s", call.name, result.success)
        return result


def _redact(arguments: dict) -> dict:
    """Strip obvious secrets from logged arguments."""
    safe = {}
    for key, value in arguments.items():
        if any(marker in key.lower() for marker in ("password", "token", "secret", "key")):
            safe[key] = "***"
        else:
            text = str(value)
            safe[key] = text[:200] + ("..." if len(text) > 200 else "")
    return safe
