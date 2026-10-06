"""Voice package.

Imports are lazy: text mode and tests must not require numpy / sounddevice /
edge-tts. Accessing an attribute (e.g. ``voice.Microphone``) imports the module
that defines it on first use.
"""
from __future__ import annotations

from typing import Any

_EXPORTS = {
    "make_tts": "voice.text_to_speech",
    "TextToSpeech": "voice.text_to_speech",
    "NullTTS": "voice.text_to_speech",
    "EdgeTTS": "voice.text_to_speech",
    "Pyttsx3TTS": "voice.text_to_speech",
    "make_stt": "voice.speech_to_text",
    "SpeechToText": "voice.speech_to_text",
    "Microphone": "voice.microphone",
    "VoiceListener": "voice.listener",
    "WakeWordDetector": "voice.wake_word",
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:  # PEP 562 lazy package attribute access
    module_path = _EXPORTS.get(name)
    if module_path is None:
        raise AttributeError(f"module 'voice' has no attribute {name!r}")
    import importlib

    module = importlib.import_module(module_path)
    value = getattr(module, name)
    globals()[name] = value  # cache for subsequent accesses
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
