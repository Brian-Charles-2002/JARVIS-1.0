"""Permission layer: the local gate between Gemini's proposal and execution.

Gemini may *propose* any action; this module decides whether JARVIS is allowed
to run it immediately, must ask first, or must refuse.
"""
from __future__ import annotations

from config.settings import Settings
from safety.confirmation import PendingAction
from safety.risk import RiskLevel, requires_confirmation
from safety.validator import describe_action
from tools.registry import ToolRegistry


class PermissionManager:
    def __init__(self, settings: Settings, registry: ToolRegistry) -> None:
        self.settings = settings
        self.registry = registry
        self.threshold = RiskLevel.parse(settings.confirmation_level)

    def risk(self, tool: str, arguments: dict) -> RiskLevel:
        return self.registry.risk_of(tool, arguments)

    def needs_confirmation(self, tool: str, arguments: dict) -> bool:
        level = self.risk(tool, arguments)
        return requires_confirmation(
            level, self.threshold, self.settings.require_confirmation_for_destructive
        )

    def build_pending(self, tool: str, arguments: dict, call_id: str | None) -> PendingAction:
        level = self.risk(tool, arguments)
        return PendingAction(
            tool=tool,
            arguments=arguments,
            risk=level,
            description=describe_action(tool, arguments),
            call_id=call_id,
        )
