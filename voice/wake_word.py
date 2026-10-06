"""Optional wake-word gating (post-transcription string matching).

Deliberately simple so it can never break the primary voice loop: when the wake
word is disabled the listener processes every utterance; when enabled,
utterances must begin with the configured word (e.g. "Jarvis, open Chrome").
"""
from __future__ import annotations

import re


class WakeWordDetector:
    def __init__(self, wake_word: str) -> None:
        self.wake_word = (wake_word or "jarvis").strip().lower()
        self._pattern = re.compile(
            r"\b" + re.escape(self.wake_word) + r"\b[\s,!.:]*", re.IGNORECASE
        )

    def detect(self, transcript: str) -> tuple[bool, str]:
        """Return (matched, command_text_without_wake_word)."""
        text = (transcript or "").strip()
        if not text:
            return False, ""
        match = self._pattern.search(text)
        if match and match.start() <= 4:  # wake word must be near the start
            command = text[match.end():].strip()
            return True, command
        return False, text
