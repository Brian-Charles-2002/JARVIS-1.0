"""MemoryManager facade: session (short-term) + persistent (long-term) memory."""
from __future__ import annotations

from config.settings import Settings
from memory.long_term import LongTermMemory
from memory.short_term import ShortTermMemory


class MemoryManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.short_term = ShortTermMemory()
        self.long_term = LongTermMemory(settings.data_dir / "memory.db")

    # --- learning user preferences -----------------------------------------
    def learn_preference(self, key: str, value) -> None:
        self.long_term.set(key, value)

    def preference(self, key: str, default=None):
        return self.long_term.get(key, default)

    def note_application(self, name: str) -> None:
        """Remember frequently used applications (best-effort, non-sensitive)."""
        self.long_term.remember_entity("application", name)

    def note_search(self, query: str) -> None:
        self.long_term.remember_entity("search", query)

    def persist_session(self) -> None:
        """Flush durable session facts (called on shutdown)."""
        if self.short_term.last_url:
            self.long_term.remember_entity("url", self.short_term.last_url)

    def close(self) -> None:
        self.persist_session()
        self.long_term.close()
