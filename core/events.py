"""Runtime events: cooperative cancellation shared between the agent and executor."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class CancellationToken:
    """Check before each significant action to honor a user 'stop'/'cancel'."""

    _event: threading.Event = field(default_factory=threading.Event)

    def cancel(self) -> None:
        self._event.set()

    def reset(self) -> None:
        self._event.clear()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def check(self) -> None:
        if self._event.is_set():
            raise TaskCancelled("The task was cancelled by the user.")


class TaskCancelled(Exception):
    """Raised when a cooperative cancellation is detected mid-task."""
