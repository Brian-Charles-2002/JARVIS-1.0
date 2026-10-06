"""Centralized configuration for JARVIS.

Settings are loaded from environment variables (and a local ``.env`` file) so
that the model, voice, safety and logging behaviour can be changed without
editing any Python source. See ``.env.example`` for the full list.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# --- Project paths (never hard-coded user home) -----------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = DATA_DIR / "logs"
SCREENSHOT_DIR = DATA_DIR / "screenshots"
CACHE_DIR = DATA_DIR / "cache"


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _get_str(name: str, default: str = "") -> str:
    raw = os.getenv(name)
    return default if raw is None else raw.strip()


@dataclass(frozen=True)
class Settings:
    """Immutable snapshot of runtime configuration."""

    # identity
    assistant_name: str = "Jarvis"

    # gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-flash-lite-latest"

    # wake word
    wake_word_enabled: bool = False
    wake_word: str = "jarvis"

    # speech-to-text
    stt_backend: str = "local"
    stt_model: str = "base.en"
    stt_compute_type: str = "int8"

    # vad / speech detection
    # SILENCE_THRESHOLD is a floor: the VAD triggers above it, or above 5x the
    # measured noise floor, whichever is higher. float32 speech RMS is ~0.01-0.05.
    silence_threshold: float = 0.004
    end_silence_duration: float = 0.8
    max_recording_duration: float = 20.0
    min_recording_duration: float = 0.4
    sample_rate: int = 16000
    microphone_device: str = ""

    # text-to-speech
    tts_engine: str = "edge"
    tts_voice: str = "en-GB-RyanNeural"
    tts_rate: int = 175
    tts_volume: float = 1.0

    # safety
    require_confirmation_for_destructive: bool = True
    confirmation_level: str = "DESTRUCTIVE"
    max_tool_retries: int = 2
    tool_timeout_seconds: int = 60

    # browser automation
    browser_headless: bool = False

    # memory / context
    max_recent_messages: int = 12
    context_summary_threshold: int = 20

    # logging
    log_level: str = "INFO"
    debug: bool = False

    # paths
    project_root: Path = field(default=PROJECT_ROOT)
    data_dir: Path = field(default=DATA_DIR)
    log_dir: Path = field(default=LOG_DIR)

    @property
    def has_gemini_key(self) -> bool:
        return bool(self.gemini_api_key)

    def ensure_runtime_dirs(self) -> None:
        """Create data directories required at runtime."""
        for directory in (self.data_dir, self.log_dir, SCREENSHOT_DIR, CACHE_DIR):
            directory.mkdir(parents=True, exist_ok=True)


def load_settings(env_file: str | os.PathLike[str] | None = None) -> Settings:
    """Load settings from the environment, optionally loading a ``.env`` file.

    A missing ``.env`` is fine — environment variables are still honored.
    """
    dotenv_path = Path(env_file) if env_file else PROJECT_ROOT / ".env"
    if dotenv_path.exists():
        load_dotenv(dotenv_path, override=False)

    settings = Settings(
        assistant_name=_get_str("ASSISTANT_NAME", "Jarvis"),
        gemini_api_key=_get_str("GEMINI_API_KEY", ""),
        gemini_model=_get_str("GEMINI_MODEL", "gemini-flash-lite-latest"),
        wake_word_enabled=_get_bool("WAKE_WORD_ENABLED", False),
        wake_word=_get_str("WAKE_WORD", "jarvis"),
        stt_backend=_get_str("STT_BACKEND", "local"),
        stt_model=_get_str("STT_MODEL", "base.en"),
        stt_compute_type=_get_str("STT_COMPUTE_TYPE", "int8"),
        silence_threshold=_get_float("SILENCE_THRESHOLD", 0.004),
        end_silence_duration=_get_float("END_SILENCE_DURATION", 0.8),
        max_recording_duration=_get_float("MAX_RECORDING_DURATION", 20.0),
        min_recording_duration=_get_float("MIN_RECORDING_DURATION", 0.4),
        sample_rate=_get_int("SAMPLE_RATE", 16000),
        microphone_device=_get_str("MICROPHONE_DEVICE", ""),
        tts_engine=_get_str("TTS_ENGINE", "edge"),
        tts_voice=_get_str("TTS_VOICE", "en-GB-RyanNeural"),
        tts_rate=_get_int("TTS_RATE", 175),
        tts_volume=_get_float("TTS_VOLUME", 1.0),
        require_confirmation_for_destructive=_get_bool(
            "REQUIRE_CONFIRMATION_FOR_DESTRUCTIVE_ACTIONS", True
        ),
        confirmation_level=_get_str("CONFIRMATION_LEVEL", "DESTRUCTIVE").upper(),
        max_tool_retries=_get_int("MAX_TOOL_RETRIES", 2),
        tool_timeout_seconds=_get_int("TOOL_TIMEOUT_SECONDS", 60),
        browser_headless=_get_bool("BROWSER_HEADLESS", False),
        max_recent_messages=_get_int("MAX_RECENT_MESSAGES", 12),
        context_summary_threshold=_get_int("CONTEXT_SUMMARY_THRESHOLD", 20),
        log_level=_get_str("LOG_LEVEL", "INFO").upper(),
        debug=_get_bool("DEBUG", False),
    )
    settings.ensure_runtime_dirs()
    return settings


def validate_settings(settings: Settings) -> None:
    """Validate required configuration, raising :class:`ConfigError` if invalid."""
    if not settings.has_gemini_key:
        raise ConfigError(
            "Gemini API key not configured.\n\n"
            "Create a .env file (copy .env.example) and add:\n\n"
            "    GEMINI_API_KEY=your_api_key\n\n"
            "Get a key at https://aistudio.google.com/apikey"
        )
    valid_levels = {"SAFE", "CAUTION", "SENSITIVE", "DESTRUCTIVE"}
    if settings.confirmation_level not in valid_levels:
        raise ConfigError(
            f"CONFIRMATION_LEVEL must be one of {sorted(valid_levels)}, "
            f"got {settings.confirmation_level!r}."
        )
