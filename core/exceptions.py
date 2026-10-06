"""Domain exceptions used across JARVIS."""
from __future__ import annotations


class JarvisError(Exception):
    """Base class for all JARVIS errors."""


class AIError(JarvisError):
    """Raised for Gemini/AI provider failures."""


class RateLimitError(AIError):
    """Raised when the provider reports a rate limit / quota problem."""


class AuthenticationError(AIError):
    """Raised for invalid or rejected API credentials."""


class ToolError(JarvisError):
    """Raised when a tool fails in an expected, structured way."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ValidationError(ToolError):
    """Raised when tool arguments fail schema validation."""


class PermissionDeniedError(JarvisError):
    """Raised when a tool is blocked by the permission layer."""


class ApplicationNotFound(ToolError):
    """Raised when an application cannot be discovered."""


class VoiceError(JarvisError):
    """Raised for microphone / transcription / TTS failures."""
