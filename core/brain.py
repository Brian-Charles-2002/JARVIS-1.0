"""Brain: assembles and runs JARVIS (startup, respond, text/voice modes).

This is the orchestrator used by ``main.py``. It wires the Gemini client, tool
registry, agent loop, memory, safety and text-to-speech, and provides both an
interactive text mode and a continuous voice mode.
"""
from __future__ import annotations

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

    # --- core interaction ---------------------------------------------------
    def speak(self, text: str) -> None:
        try:
            self.tts.speak(text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Speak failed: %s", exc)

    def process(self, text: str, speak: bool = True) -> tuple[str, bool]:
        """Handle one utterance. Returns (reply, keep_going)."""
        stripped = (text or "").strip()
        lowered = stripped.lower()

        if lowered in _EXIT:
            reply = "Goodbye. Shutting down."
            print(f"{self.settings.assistant_name}: {reply}")
            if speak:
                self.speak(reply)
            return reply, False

        if lowered in _CANCEL:
            self.agent.cancel()
            reply = "Cancelled."
            print(f"{self.settings.assistant_name}: {reply}")
            if speak:
                self.speak(reply)
            return reply, True

        if lowered in _STATUS:
            task = self.agent.task
            reply = self._status_text(task)
            print(f"{self.settings.assistant_name}: {reply}")
            if speak:
                self.speak(reply)
            return reply, True

        result = self.agent.handle_text(stripped, self.token)
        print(f"{self.settings.assistant_name}: {result.text}")
        if speak:
            self.speak(result.text)
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
        print(f"{self.settings.assistant_name}: {text}")
        self.speak(text)

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
