"""Context management: bounded history + structured session context + summaries.

Prevents the prompt from growing without limit. Recent turns are kept verbatim;
older turns are summarized (via the AI) once a threshold is crossed, and a
compact structured view of session memory is injected as context.
"""
from __future__ import annotations

from typing import Callable

from config.settings import Settings
from core.conversation import Conversation
from memory.short_term import ShortTermMemory

# A summarizer maps a list of old ChatMessages to a short text summary.
Summarizer = Callable[[list], str]


class ContextManager:
    def __init__(self, settings: Settings, short_term: ShortTermMemory) -> None:
        self.settings = settings
        self.short_term = short_term

    def keep_recent(self, conversation: Conversation) -> None:
        """Fold older turns into a rolling summary to bound context size."""
        threshold = self.settings.context_summary_threshold
        if len(conversation.messages) <= threshold:
            return
        keep = self.settings.max_recent_messages
        old, recent = conversation.messages[:-keep], conversation.messages[-keep:]
        if old:
            conversation.summary = self._fold_summary(conversation.summary, old)
        conversation.messages = recent

    @staticmethod
    def _fold_summary(existing: str | None, old_messages: list) -> str:
        """Cheap deterministic fold. A richer (Gemini) summarizer can replace this."""
        lines = [f"Earlier conversation summary: {existing}"] if existing else []
        for message in old_messages:
            text = message.plain_text()
            if text:
                who = "User" if message.role == "user" else "Jarvis"
                lines.append(f"{who}: {text[:200]}")
        return " | ".join(lines)[-1200:]

    def structured_context(self) -> str:
        """Render session memory as a compact block for the system instruction."""
        snapshot = self.short_term.to_context_dict()
        if not snapshot:
            return ""
        lines = ["[SESSION CONTEXT - resolve 'it/there/that folder' from these]"]
        for key, value in snapshot.items():
            lines.append(f"- {key}: {value}")
        return "\n".join(lines)
