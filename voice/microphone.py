"""Microphone capture with energy-based voice activity detection.

The VAD threshold is calibrated from the measured noise floor instead of being a
fixed absolute level: float32 microphone RMS for normal speech is usually in the
0.01-0.05 range, so any hard-coded absolute threshold is either deaf or twitchy
depending on the device and the Windows input volume.

Records until the speaker stops (end-of-speech silence) or the max duration is
reached. Waiting for speech to start is not capped by that duration, so JARVIS
keeps listening as long as you need. Uses sounddevice.
"""
from __future__ import annotations

from collections import deque
from typing import Callable

import numpy as np

from config.settings import Settings
from core.logging_setup import get_logger

logger = get_logger("voice.mic")

# How far above the noise floor speech must rise to count as speech.
_NOISE_MULTIPLIER = 5.0
_NOISE_MARGIN = 0.003
# Blocks of audio kept before onset so the first phoneme is not clipped.
_PREROLL_BLOCKS = 5


def _rms(frame: np.ndarray) -> float:
    if frame.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(frame.astype(np.float32)))))


class Microphone:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.sample_rate = settings.sample_rate
        self.blocksize = int(self.sample_rate * 0.03)  # 30ms blocks
        self.block_seconds = self.blocksize / self.sample_rate
        # Treated as a floor: detection never triggers below this level.
        self.threshold_floor = settings.silence_threshold
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
        logger.warning("Microphone device %r not found; using the system default.", name)
        return None

    def available(self) -> bool:
        try:
            import sounddevice  # type: ignore

            return any(d.get("max_input_channels", 0) > 0 for d in sounddevice.query_devices())
        except Exception:  # noqa: BLE001
            return False

    def _threshold(self, noise: float) -> float:
        return max(self.threshold_floor, noise * _NOISE_MULTIPLIER + _NOISE_MARGIN)

    def record_utterance(self, should_stop: Callable[[], bool] | None = None) -> np.ndarray:
        """Block until one spoken utterance is captured. Returns float32 mono."""
        import sounddevice as sd  # type: ignore

        noise = 0.0
        threshold = self._threshold(noise)
        onset_blocks = 0
        needed_onset = 3
        preroll: deque[np.ndarray] = deque(maxlen=_PREROLL_BLOCKS)
        frames: list[np.ndarray] = []
        silence_blocks = 0
        speech_blocks = 0
        speech_started = False
        max_speech_blocks = int(self.max_duration / self.block_seconds)
        min_speech_blocks = int(self.min_duration / self.block_seconds)
        idle_blocks = 0
        quiet_samples: deque[float] = deque(maxlen=25)  # ~0.75s trailing window

        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=self.blocksize,
            device=self._device(),
        ) as stream:
            while True:
                if should_stop and should_stop():
                    break
                data, _ = stream.read(self.blocksize)
                frame = data[:, 0]
                energy = _rms(frame)

                if not speech_started:
                    # Keep the noise estimate honest while nobody is talking.
                    if energy < threshold:
                        quiet_samples.append(energy)
                        if len(quiet_samples) >= 8:
                            noise = float(np.median(quiet_samples))
                            threshold = self._threshold(noise)
                        preroll.append(frame)
                        onset_blocks = 0
                        idle_blocks += 1
                        if idle_blocks == int(5 / self.block_seconds):
                            logger.info(
                                "No speech yet: noise floor %.5f, speech threshold %.5f, "
                                "loudest block in the last second %.5f. If you were talking, "
                                "raise your Windows input volume.",
                                noise, threshold, max(quiet_samples or [0.0]),
                            )
                        continue
                    preroll.append(frame)
                    onset_blocks += 1
                    if onset_blocks < needed_onset:
                        continue
                    speech_started = True
                    frames = list(preroll)[:-1]
                    logger.debug("Speech onset detected at threshold %.5f.", threshold)

                frames.append(frame)
                speech_blocks += 1
                if energy >= threshold:
                    silence_blocks = 0
                else:
                    silence_blocks += 1
                    if silence_blocks * self.block_seconds >= self.end_silence:
                        break
                if speech_blocks >= max_speech_blocks:
                    break

        if not speech_started or not frames:
            return np.zeros(0, dtype=np.float32)
        audio = np.concatenate(frames).astype(np.float32)
        if len(audio) < min_speech_blocks * self.blocksize:
            logger.debug("Discarded a %.2fs fragment as too short.", len(audio) / self.sample_rate)
            return np.zeros(0, dtype=np.float32)
        return audio
