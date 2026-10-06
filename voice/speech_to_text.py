"""Speech-to-text. Local faster-whisper (default) or Google Web Speech via
SpeechRecognition. The Whisper model is loaded once and reused.
"""
from __future__ import annotations

import threading
from abc import ABC, abstractmethod

import numpy as np

from config.settings import Settings
from core.exceptions import VoiceError
from core.logging_setup import get_logger

logger = get_logger("voice.stt")


class SpeechToText(ABC):
    @abstractmethod
    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str: ...

    def warmup(self) -> None:  # pragma: no cover - optional
        pass


class WhisperSTT(SpeechToText):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._model = None
        self._lock = threading.Lock()

    def _ensure(self):
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel  # type: ignore

            logger.info("Loading faster-whisper model '%s'...", self.settings.stt_model)
            self._model = WhisperModel(
                self.settings.stt_model,
                device="auto",
                compute_type=self.settings.stt_compute_type,
            )
            return self._model
        except Exception as exc:  # noqa: BLE001
            raise VoiceError(f"faster-whisper unavailable: {exc}") from exc

    def warmup(self) -> None:
        with self._lock:
            self._ensure()

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        with self._lock:
            model = self._ensure()
            audio = np.asarray(audio, dtype=np.float32)
            if sample_rate != 16000:
                audio = _resample(audio, sample_rate, 16000)
            segments, _ = model.transcribe(audio, language=None, vad_filter=True)
            return " ".join(seg.text.strip() for seg in segments).strip()


class RecognitionSTT(SpeechToText):
    """Uses the SpeechRecognition Google backend over in-memory audio (no key)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        import speech_recognition as sr  # type: ignore

        audio = np.asarray(audio, dtype=np.float32)
        pcm16 = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
        recognizer = sr.Recognizer()
        data = sr.AudioData(pcm16, sample_rate, 2)
        try:
            return recognizer.recognize_google(data).strip()
        except sr.UnknownValueError:
            return ""
        except sr.RequestError as exc:  # noqa: BLE001
            raise VoiceError(f"SpeechRecognition request failed: {exc}") from exc


def _resample(audio: np.ndarray, orig: int, target: int) -> np.ndarray:
    if orig == target:
        return audio
    duration = len(audio) / orig
    new_len = int(duration * target)
    indices = np.linspace(0, len(audio) - 1, new_len)
    return np.interp(indices, np.arange(len(audio)), audio).astype(np.float32)


def make_stt(settings: Settings) -> SpeechToText:
    if (settings.stt_backend or "local").lower() == "recognition":
        return RecognitionSTT(settings)
    return WhisperSTT(settings)
