"""Text-to-speech with pluggable engines.

EdgeTTS gives natural Windows-friendly voices; Pyttsx3 is an offline fallback.
speak() is synchronous and blocks until playback finishes so the microphone can
be paused while JARVIS talks (prevents it hearing itself). All engines degrade
to a no-op rather than crashing when audio hardware or the network is absent.
"""
from __future__ import annotations

import asyncio
import tempfile
import threading
from abc import ABC, abstractmethod
from pathlib import Path

from config.settings import Settings
from core.logging_setup import get_logger

logger = get_logger("voice.tts")


class TextToSpeech(ABC):
    @abstractmethod
    def speak(self, text: str) -> None: ...

    def shutdown(self) -> None:  # pragma: no cover - optional
        pass


class NullTTS(TextToSpeech):
    def speak(self, text: str) -> None:
        return


class EdgeTTS(TextToSpeech):
    def __init__(self, settings: Settings) -> None:
        self.voice = settings.tts_voice
        self._mixer_ready = False
        self._lock = threading.Lock()
        self._init_audio()

    def _init_audio(self) -> None:
        try:
            import pygame  # type: ignore

            pygame.mixer.init()
            self._mixer_ready = True
        except Exception as exc:  # noqa: BLE001 - no audio device / SDL
            logger.warning("pygame mixer unavailable: %s", exc)

    def _stream(self, text: str) -> bytes:
        import edge_tts  # type: ignore

        async def run() -> bytes:
            buffer = bytearray()
            communicate = edge_tts.Communicate(text, self.voice)
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    buffer.extend(chunk["data"])
            return bytes(buffer)

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(run())
        finally:
            loop.close()

    def speak(self, text: str) -> None:
        text = (text or "").strip()
        if not text or not self._mixer_ready:
            return
        import time

        try:
            with self._lock:
                import pygame  # type: ignore

                audio = self._stream(text)
                if not audio:
                    return
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as handle:
                    handle.write(audio)
                    tmp = Path(handle.name)
                try:
                    pygame.mixer.music.load(str(tmp))
                    pygame.mixer.music.play()
                    while pygame.mixer.music.get_busy():
                        time.sleep(0.05)
                finally:
                    if hasattr(pygame.mixer.music, "unload"):
                        pygame.mixer.music.unload()
                    tmp.unlink(missing_ok=True)
        except Exception as exc:  # noqa: BLE001 - TTS must never crash the assistant
            logger.warning("EdgeTTS playback failed: %s", exc)


class Pyttsx3TTS(TextToSpeech):
    def __init__(self, settings: Settings) -> None:
        self.rate = settings.tts_rate
        self.volume = max(0.0, min(1.0, settings.tts_volume))
        self._engine = None
        try:
            import pyttsx3  # type: ignore

            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", self.rate)
            self._engine.setProperty("volume", self.volume)
        except Exception as exc:  # noqa: BLE001
            logger.warning("pyttsx3 init failed: %s", exc)

    def speak(self, text: str) -> None:
        text = (text or "").strip()
        if not text or self._engine is None:
            return
        try:
            self._engine.say(text)
            self._engine.runAndWait()
        except Exception as exc:  # noqa: BLE001
            logger.warning("pyttsx3 speak failed: %s", exc)


def make_tts(settings: Settings) -> TextToSpeech:
    engine = (settings.tts_engine or "edge").lower()
    if engine == "edge":
        return EdgeTTS(settings)
    if engine == "pyttsx3":
        return Pyttsx3TTS(settings)
    if engine == "none":
        return NullTTS()
    return EdgeTTS(settings)
