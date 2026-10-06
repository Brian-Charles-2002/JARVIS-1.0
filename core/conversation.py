"""Provider-agnostic conversation state.

Messages are stored as generic parts (text / function call / function response)
so the Gemini adapter can translate them into SDK types. Keeping this free of
`google.genai` imports lets another AI provider be added later (see README).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChatPart:
    text: str | None = None
    function_call: dict[str, Any] | None = None
    function_response: dict[str, Any] | None = None


@dataclass
class ChatMessage:
    role: str  # "user" or "model"
    parts: list[ChatPart] = field(default_factory=list)

    def plain_text(self) -> str:
        return "".join(p.text for p in self.parts if p.text)


class Conversation:
    """Ordered chat turns with helpers for the agent loop."""

    def __init__(self) -> None:
        self.messages: list[ChatMessage] = []
        self.summary: str | None = None

    # --- builders ----------------------------------------------------------
    def add_user(self, text: str) -> None:
        self.messages.append(ChatMessage(role="user", parts=[ChatPart(text=text)]))

    def add_model_text(self, text: str) -> None:
        if text:
            self.messages.append(ChatMessage(role="model", parts=[ChatPart(text=text)]))

    def add_model_function_calls(self, calls: list[dict[str, Any]]) -> None:
        """calls: list of {name, args}."""
        parts = [ChatPart(function_call={"name": c["name"], "args": c.get("args", {}),
                                         "id": c.get("id") or _call_id()}) for c in calls]
        self.messages.append(ChatMessage(role="model", parts=parts))

    def add_function_response(self, name: str, response: dict[str, Any], call_id: str | None = None) -> None:
        # function responses travel as a user-role turn per Gemini's protocol.
        self.messages.append(ChatMessage(
            role="user",
            parts=[ChatPart(function_response={"name": name, "response": response, "id": call_id})],
        ))

    def recent_messages(self, count: int) -> list[ChatMessage]:
        return self.messages[-count:]

    def all_messages(self) -> list[ChatMessage]:
        return list(self.messages)

    def __len__(self) -> int:
        return len(self.messages)


def _call_id() -> str:
    return "call_" + uuid.uuid4().hex[:8]
