"""Brain: assembles and runs JARVIS (startup, respond, text/voice modes).

This is the orchestrator used by ``main.py``. It wires the Gemini client, tool
registry, agent loop, memory, safety and text-to-speech, and provides both an
interactive text mode and a continuous voice mode.
"""
from __future__ import annotations

from typing import Callable

from config.settings import Settings, validate_settings
from ai.gemini_client import GeminiClient
from core.agent import Agent
from core.events import CancellationToken
from core.logging_setup import get_logger
from core.memory import MemoryManager
from tools import build_registry
from voice.text_to_speech import make_tts, TextToSpeech

logger = get_logger("core.brain")

_EXIT = {"exit jarvis", "shutdown jarvis", "quit jarvis", "goodbye jarvis",
         "exit", "quit", "goodbye"}
_CANCEL = {"stop", "cancel", "cancel task", "cancel that", "stop that",
           "never mind", "nevermind"}
_STATUS = {"what are you doing?", "what are you doing", "status", "what's happening"}


class Brain:
    def __init__(self, settings: Settings) -> None:
        validate_settings(settings)
        self.settings = settings
        self.client = GeminiClient(settings)
        self.registry = build_registry(settings, client=self.client)
        self.memory = MemoryManager(settings)
        self.agent = Agent(settings, self.client, self.registry, self.memory)
        self.tts: TextToSpeech = make_tts(settings)
        self.token = CancellationToken()
        # Optional observer used by the graphical UI: called with small dicts
        # describing state/text so a front-end can animate and transcribe.
        self.on_event: Callable[[dict], None] | None = None

    def _emit(self, event: dict) -> None:
        callback = self.on_event
        if callback:
            try:
                callback(event)
            except Exception:  # noqa: BLE001 - a UI glitch must never break the assistant
                logger.debug("on_event callback raised", exc_info=True)

    # --- startup ------------------------------------------------------------
    def startup_checks(self) -> list[tuple[str, bool]]:
        """Validate configuration and connectivity; returns status lines."""
        checks: list[tuple[str, bool]] = []
        checks.append(("Configuration loaded", True))
        checks.append(("Gemini connected", self.client.health_check()))
        checks.append(("Tool registry loaded", len(self.registry.names) > 0))
        checks.append(("Text-to-speech ready", self.settings.tts_engine != "none"))
        return checks

    def greeting(self) -> str:
        from tools.misc import GetCurrentTime

        info = GetCurrentTime().run().result or {}
        greeting = info.get("greeting", "Hello")
        name = self.settings.assistant_name
        return f"{greeting}. {name.upper()} online. How can I help?"

    def announce(self, text: str, speak: bool = True) -> None:
        """Emit/print/speak a line that is not in reply to user input (greetings)."""
        self._respond(text, speak)

    # --- core interaction ---------------------------------------------------
    def speak(self, text: str) -> None:
        try:
            self.tts.speak(text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Speak failed: %s", exc)

    def _respond(self, reply: str, speak: bool) -> None:
        """Print, emit and optionally speak one assistant reply."""
        print(f"{self.settings.assistant_name}: {reply}")
        self._emit({"type": "reply", "text": reply})
        if speak:
            self._emit({"type": "state", "state": "speaking"})
            self.speak(reply)
        self._emit({"type": "state", "state": "idle"})

    def process(self, text: str, speak: bool = True) -> tuple[str, bool]:
        """Handle one utterance. Returns (reply, keep_going)."""
        stripped = (text or "").strip()
        lowered = stripped.lower()
        if stripped:
            self._emit({"type": "user", "text": stripped})

        if lowered in _EXIT:
            self._respond("Goodbye. Shutting down.", speak)
            return "Goodbye. Shutting down.", False

        if lowered in _CANCEL:
            self.agent.cancel()
            self._respond("Cancelled.", speak)
            return "Cancelled.", True

        if lowered in _STATUS:
            reply = self._status_text(self.agent.task)
            self._respond(reply, speak)
            return reply, True

        self._emit({"type": "state", "state": "thinking"})
        result = self.agent.handle_text(stripped, self.token)
        self._respond(result.text, speak)
        return result.text, True

    def _status_text(self, task) -> str:
        if not task:
            return "I'm idle and ready."
        from core.planner import TaskStatus

        if task.status == TaskStatus.WAITING_FOR_CONFIRMATION:
            return "I'm waiting for you to confirm an action. Say yes or no."
        done = task.completed_steps
        return f"I'm working on: {task.objective}. {len(task.steps)} step(s) so far."

    # --- modes --------------------------------------------------------------
    def run_text_mode(self) -> None:
        """Interactive terminal chat (no microphone)."""
        name = self.settings.assistant_name
        self._print_and_speak(self.greeting())
        while True:
            try:
                text = input("You > ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not text:
                continue
            _, keep = self.process(text)
            if not keep:
                break
        self.close()

    def _print_and_speak(self, text: str) -> None:
        self._respond(text, speak=True)

    def run_voice_mode(self) -> None:
        from voice.listener import VoiceListener
        from voice.microphone import Microphone
        from voice.speech_to_text import make_stt

        name = self.settings.assistant_name
        stt = make_stt(self.settings)
        mic = Microphone(self.settings)
        if not mic.available():
            logger.warning("No microphone available; falling back to text mode.")
            print("[!] Microphone not available. Use --text mode.")
            self.run_text_mode()
            return

        logger.info("Warming up speech-to-text model...")
        try:
            stt.warmup()
        except Exception as exc:  # noqa: BLE001 - missing whisper backend shouldn't crash startup
            message = (
                "Speech-to-text isn't ready on this machine yet "
                f"({exc}). Install it with 'pip install faster-whisper sounddevice numpy', "
                "or run in text mode with 'python main.py --text'."
            )
            logger.warning(message)
            print(f"[!] {message}")
            self.close()
            return

        self._print_and_speak(self.greeting())

        listener = VoiceListener(self.settings, stt, mic)

        def on_text(text: str) -> bool:
            print(f"You: {text}")
            _, keep = self.process(text)
            return keep

        try:
            listener.run(on_text)
        except KeyboardInterrupt:
            pass
        finally:
            self.close()

    def close(self) -> None:
        try:
            from tools.browser_manager import shutdown_manager

            shutdown_manager()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.memory.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.tts.shutdown()
        except Exception:  # noqa: BLE001
            pass
