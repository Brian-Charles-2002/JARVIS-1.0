"""JARVIS entrypoint.

    python main.py            # voice mode (needs microphone + Whisper)
    python main.py --text     # text/debug chat mode (no microphone)
    python main.py --debug    # verbose logging

Starts the assistant, runs startup checks, speaks a greeting and enters the
chosen interaction loop. Exits cleanly on Ctrl+C or "exit jarvis".
"""
from __future__ import annotations

import argparse
import sys
import warnings

from config.settings import ConfigError, load_settings
from core.logging_setup import setup_logging, get_logger

# The google-genai SDK emits an advisory warning about automatic function
# calling; JARVIS handles function calls manually, so this note is not useful.
warnings.filterwarnings(
    "ignore",
    message=r"Direct use of automatic function calling.*",
    category=UserWarning,
)


def _configure_console() -> None:
    """Force UTF-8 on Windows consoles so the banner renders reliably."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass

BANNER = r"""
==================================================
                     J.A.R.V.I.S
              Personal AI Assistant
==================================================
"""


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="JARVIS - personal AI desktop assistant")
    parser.add_argument("--text", action="store_true", help="run in text mode (no microphone)")
    parser.add_argument("--voice", action="store_true", help="run in voice mode (default)")
    parser.add_argument("--debug", action="store_true", help="enable verbose debug logging")
    parser.add_argument("--no-speak", action="store_true", help="disable text-to-speech")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    _configure_console()
    args = parse_args(argv)

    settings = load_settings()
    if args.debug:
        from dataclasses import replace

        settings = replace(settings, debug=True, log_level="DEBUG")
    if args.no_speak:
        from dataclasses import replace

        settings = replace(settings, tts_engine="none")

    setup_logging(settings.log_dir, settings.log_level, settings.debug)
    logger = get_logger("main")

    print(BANNER.strip())

    # Import brain after logging so SDK import errors are reported cleanly.
    from config.settings import validate_settings
    from core.brain import Brain

    try:
        validate_settings(settings)
    except ConfigError as exc:
        print(f"\n[!] {exc}\n")
        logger.error("Configuration error: %s", exc)
        return 2

    try:
        brain = Brain(settings)
    except Exception as exc:  # noqa: BLE001
        print(f"\n[!] Failed to initialize JARVIS: {exc}\n")
        logger.exception("Initialization failed")
        return 1

    # Startup checklist
    checks = brain.startup_checks()
    for label, ok in checks:
        print(f"[{'✓' if ok else '✗'}] {label}")

    if not dict(checks).get("Gemini connected"):
        print("\n[!] Could not reach Gemini. Check GEMINI_API_KEY / GEMINI_MODEL and network.")

    print()
    try:
        if args.text:
            brain.run_text_mode()
        else:
            brain.run_voice_mode()
    except KeyboardInterrupt:
        print("\n[Jarvis] Interrupted. Shutting down.")
    finally:
        brain.close()
        logger.info("JARVIS exited.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
