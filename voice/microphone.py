"""Microphone capture with simple energy-based voice activity detection.

Records only until the speaker stops (end-of-speech silence) or a max duration
is reached - not a fixed arbitrary length. Uses sounddevice.
"""
from __future__ import annotations

from collections import deque
from typing import Callable

import numpy as np

from config.settings import Settings
from core.exceptions import VoiceError
from core.logging_setup import get_logger

logger = get_logger("voice.mic")


def _rms(frame: np.ndarray) -> float:
    if frame.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(frame.astype(np.float32)))))


class Microphone:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.sample_rate = settings.sample_rate
        self.blocksize = int(self.sample_rate * 0.03)  # 30ms blocks
        self.threshold = settings.silence_threshold
        self.end_silence = settings.end_silence_duration
        self.max_duration = settings.max_recording_duration
        self.min_duration = settings.min_recording_duration

    def _device(self):
        name = self.settings.microphone_device
        if not name:
            return None
        import sounddevice as sd  # type: ignore

        for i, dev in enumerate(sd.query_devices()):
            if dev.get("max_input_channels", 0) > 0 and name.lower() in dev["name"].lower():
                return i
        return None

    def available(self) -> bool:
        try:
            import sounddevice  # type: ignore

            return any(d.get("max_input_channels", 0) > 0 for d in sounddevice.query_devices())
        except Exception:  # noqa: BLE001
            return False

    def record_utterance(self, should_stop: Callable[[], bool] | None = None) -> np.ndarray:
        """Block until one spoken utterance is captured. Returns float32 mono."""
        import sounddevice as sd  # type: ignore

        frames: list[np.ndarray] = []
        silence_blocks = 0
        speech_started = False
        total_blocks = int(self.max_duration / (self.blocksize / self.sample_rate))
        min_speech_blocks = int(self.min_duration / (self.blocksize / self.sample_rate))
        # require a tiny onset of sustained energy to avoid a single click
        onset_blocks = 0

        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=self.blocksize,
            device=self._device(),
        ) as stream:
            for _ in range(total_blocks):
                if should_stop and should_stop():
                    break
                data, _ = stream.read(self.blocksize)
                frame = data[:, 0]
                energy = _rms(frame)
                if not speech_started:
                    if energy >= self.threshold:
                        onset_blocks += 1
                        if onset_blocks >= 3:  # sustained onset
                            speech_started = True
                            frames.append(frame)
                        else:
                            frames.append(frame)  # keep onset audio
                    else:
                        onset_blocks = 0
                        frames.clear()
                else:
                    frames.append(frame)
                    if energy < self.threshold:
                        silence_blocks += 1
                        if silence_blocks * (self.blocksize / self.sample_rate) >= self.end_silence:
                            break
                    else:
                        silence_blocks = 0

        audio = np.concatenate(frames) if frames else np.zeros(0, dtype=np.float32)
        if len(audio) < min_speech_blocks * self.blocksize:
            return np.zeros(0, dtype=np.float32)
        return audio.astype(np.float32)
