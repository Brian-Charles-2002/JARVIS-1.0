"""Pending-action confirmation system.

Risky tool calls are not executed immediately. They are staged as a
:class:`PendingAction`, the assistant asks the user, and the very next utterance
is interpreted as confirmation or cancellation - the pending action is never
forgotten.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from safety.risk import RiskLevel

_AFFIRM = re.compile(
    r"^\s*(yes|yep|yeah|yup|do it|go ahead|confirm|confirmed|proceed|sure|ok|okay|please do|do)\b",
    re.IGNORECASE,
)
_NEGATE = re.compile(
    r"^\s*(no|nope|cancel|don't|dont|do not|stop|abort|never mind|nevermind|negative)\b",
    re.IGNORECASE,
)


@dataclass
class PendingAction:
    tool: str
    arguments: dict[str, Any]
    risk: RiskLevel
    description: str
    call_id: str | None = None

    def summary(self) -> str:
        return self.description or f"Run {self.tool}({self.arguments})"


@dataclass
class ConfirmationManager:
    pending: PendingAction | None = None

    def stage(self, action: PendingAction) -> None:
        self.pending = action

    def has_pending(self) -> bool:
        return self.pending is not None

    def take(self) -> PendingAction | None:
        action, self.pending = self.pending, None
        return action

    def clear(self) -> None:
        self.pending = None

    @staticmethod
    def interpret(text: str) -> str:
        """Return 'yes' | 'no' | 'other' for a user reply."""
        if _AFFIRM.match(text or ""):
            return "yes"
        if _NEGATE.match(text or ""):
            return "no"
        return "other"
