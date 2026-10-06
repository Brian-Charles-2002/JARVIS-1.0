"""Continuous voice loop: record -> transcribe -> hand text to the assistant.

The microphone is only active while waiting for the user (recording returns
before each response is spoken), so JARVIS never transcribes its own voice.
"""
from __future__ import annotations

from typing import Callable

from config.settings import Settings
from core.logging_setup import get_logger
from voice.microphone import Microphone
from voice.speech_to_text import SpeechToText
from voice.wake_word import WakeWordDetector

logger = get_logger("voice.listener")

OnText = Callable[[str], bool]  # returns False to stop the loop


class VoiceListener:
    def __init__(self, settings: Settings, stt: SpeechToText, mic: Microphone) -> None:
        self.settings = settings
        self.stt = stt
        self.mic = mic
        self.wake = WakeWordDetector(settings.wake_word) if settings.wake_word_enabled else None
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self, on_text: OnText) -> None:
        logger.info("Voice loop started (wake word %s).",
                    "enabled" if self.wake else "disabled")
        while not self._stop:
            try:
                audio = self.mic.record_utterance(should_stop=lambda: self._stop)
                if audio.size == 0:
                    continue
                text = self.stt.transcribe(audio, self.settings.sample_rate)
                if not text:
                    continue
                if self.wake:
                    matched, command = self.wake.detect(text)
                    if not matched:
                        continue
                    text = command
                    if not text:
                        continue
                logger.info("Heard: %s", text)
                if on_text(text) is False:
                    break
            except KeyboardInterrupt:
                break
            except Exception as exc:  # noqa: BLE001 - one bad utterance must not kill the loop
                logger.warning("Voice loop error: %s", exc)
                continue
