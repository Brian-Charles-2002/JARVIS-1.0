"""Logging configuration with rotating file output and secret redaction."""
from __future__ import annotations

import logging
import logging.handlers
import re
from pathlib import Path

# Patterns that must never appear in logs.
_REDACTIONS = [
    (re.compile(r"""(?i)(GEMINI_API_KEY\s*[=:]\s*)\S+"""), r"\1***REDACTED***"),
    (re.compile(r"""AIza[0-9A-Za-z_\-]{20,}"""), "***REDACTED_KEY***"),
    (re.compile(r"""(?i)(api[_-]?key['"]?\s*[=:]\s*)\S+"""), r"\1***"),
    (re.compile(r"""(?i)(password|token|secret|credential['"]?\s*[=:]\s*)\S+"""), r"\1***"),
]


class RedactingFormatter(logging.Formatter):
    """Formatter that scrubs known secret patterns from every record."""

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        for pattern, replacement in _REDACTIONS:
            message = pattern.sub(replacement, message)
        return message


def setup_logging(log_dir: Path, level: str = "INFO", debug: bool = False) -> logging.Logger:
    """Configure the root ``jarvis`` logger. Safe to call once at startup."""
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("jarvis")
    if getattr(logger, "_jarvis_configured", False):
        return logger

    logger.setLevel(logging.DEBUG if debug else getattr(logging, level, logging.INFO))
    fmt = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
    formatter = RedactingFormatter(fmt)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.setLevel(logging.DEBUG if debug else getattr(logging, level, logging.INFO))
    logger.addHandler(console)

    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "jarvis.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)

    logger._jarvis_configured = True  # type: ignore[attr-defined]
    return logger


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the ``jarvis`` namespace."""
    return logging.getLogger(f"jarvis.{name}")
