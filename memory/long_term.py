"""Long-term persistent memory (SQLite-backed preferences/entities).

Sensitive values (passwords, tokens, keys) are refused by design. The
:class:`MemoryProvider` abstraction makes it possible to swap in a vector
database later without touching callers.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from memory.storage import SqliteStore

# Keys/values that must never be persisted.
_SENSITIVE_KEY = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|private[_-]?key|credential|"
    r"bank|card|cvv|auth)",
    re.IGNORECASE,
)
# Known preference keys JARVIS may learn about the user.
PREFERENCE_KEYS = {
    "preferred_browser", "preferred_editor", "preferred_terminal",
    "voice", "speech_rate", "wake_word", "confirmation_level",
    "assistant_name", "app_aliases",
}


class MemoryProvider(ABC):
    """Abstract persistence provider (enables a future vector store)."""

    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any: ...

    @abstractmethod
    def set(self, key: str, value: Any) -> None: ...


class LongTermMemory(MemoryProvider):
    def __init__(self, db_path: Path) -> None:
        self._store = SqliteStore(db_path)

    @staticmethod
    def _is_sensitive(key: str, value: Any) -> bool:
        if _SENSITIVE_KEY.search(str(key)):
            return True
        text = str(value).lower()
        return any(marker in text for marker in ("password:", "api_key=", "token=", "aiza"))

    def get(self, key: str, default: Any = None) -> Any:
        return self._store.get(key, default)

    def set(self, key: str, value: Any) -> None:
        if self._is_sensitive(key, value):
            # Silently refuse to persist secret-like data.
            return
        self._store.set(key, value)

    def all_keys(self) -> list[str]:
        return self._store.all_keys()

    def remember_entity(self, kind: str, value: str) -> None:
        self._store.remember_entity(kind, value)

    def recent_entities(self, kind: str, limit: int = 10) -> list[str]:
        return self._store.recent_entities(kind, limit)

    def close(self) -> None:
        self._store.close()
