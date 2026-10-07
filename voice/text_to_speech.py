"""Text-to-speech with pluggable engines.

EdgeTTS gives natural Windows-friendly voices; Pyttsx3 is an offline fallback.

Speech is blocking by contract: ``speak()`` and ``SpeechStream.finish()`` both
return only once audio has finished playing, so the microphone stays closed
while JARVIS talks and it never transcribes its own voice.

To keep that contract while still sounding quick, ``begin_stream()`` returns a
handle that accepts the reply *as it is being generated*. Each complete
sentence is synthesized and queued the moment it lands, so playback starts on
the first sentence instead of waiting for the whole answer.
"""
from __future__ import annotations

import asyncio
import queue
import re
import tempfile
import threading
from abc import ABC, abstractmethod
from pathlib import Path

from config.settings import Settings
from core.logging_setup import get_logger

logger = get_logger("voice.tts")

# A speakable chunk needs a terminator and enough text to be worth its own
# synthesis round trip; shorter openings ("Done.") are folded into the next
# sentence rather than played alone.
_MIN_CHUNK = 12
_CHUNK_RE = re.compile(r"^(?P<head>.{%d,}?[.!?])(?:\s|$)" % _MIN_CHUNK, re.DOTALL)
# No terminator yet and the reply is already long: cut at the last whole word.
_FORCED_FLUSH = 400


class SpeechStream:
    """Incremental speech for one reply. Feed text as it arrives, then finish."""

    def feed(self, delta: str) -> None: ...

    def finish(self) -> None:
        """Flush and block until every queued sentence has been played."""

    @property
    def spoke(self) -> bool:
        """True when this stream actually produced audio."""
        return False


class BufferedSpeechStream(SpeechStream):
    """Fallback that accumulates the reply and speaks it in one go."""

    def __init__(self, engine: TextToSpeech) -> None:
        self._engine = engine
        self._parts: list[str] = []
        self._spoke = False

    def feed(self, delta: str) -> None:
        if delta:
            self._parts.append(delta)

    def finish(self) -> None:
        text = "".join(self._parts).strip()
        if text:
            self._engine.speak(text)
            self._spoke = True

    @property
    def spoke(self) -> bool:
        return self._spoke


class TextToSpeech(ABC):
    @abstractmethod
    def speak(self, text: str) -> None: ...

    def begin_stream(self) -> SpeechStream:
        return BufferedSpeechStream(self)

    def warmup(self) -> None:
        """Prime anything expensive that the first real reply would otherwise pay."""

    def shutdown(self) -> None:  # pragma: no cover - optional
        pass


class NullTTS(TextToSpeech):
    def speak(self, text: str) -> None:
        return


class EdgeSpeechStream(SpeechStream):
    """Synthesizes and plays each sentence while the reply is still streaming."""

    def __init__(self, engine: EdgeTTS) -> None:
        self._engine = engine
        self._buffer = ""
        self._chunks: queue.Queue[str | None] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._spoke = False
        self._closed = False
        self._given_up = False

    def feed(self, delta: str) -> None:
        if not delta or self._closed or self._given_up:
            return
        self._buffer += delta
        while True:
            match = _CHUNK_RE.match(self._buffer)
            if match is None:
                if len(self._buffer) >= _FORCED_FLUSH:
                    # Cut near the boundary at a word break, so an unpunctuated
                    # reply still starts playing instead of buffering whole.
                    cut = self._buffer.rfind(" ", 0, _FORCED_FLUSH)
                    if cut <= 0:
                        cut = _FORCED_FLUSH
                    head, self._buffer = self._buffer[:cut], self._buffer[cut:].lstrip()
                    self._enqueue(head.strip())
                    continue
                return
            head = match.group("head").strip()
            self._buffer = self._buffer[match.end():]
            self._enqueue(head)

    def finish(self) -> None:
        if self._closed:
            return
        self._closed = True
        remainder = self._buffer.strip()
        self._buffer = ""
        if remainder:
            self._enqueue(remainder)
        if self._worker is not None:
            self._chunks.put(None)
            self._worker.join()

    @property
    def spoke(self) -> bool:
        return self._spoke

    def _enqueue(self, sentence: str) -> None:
        if not sentence:
            return
        if self._worker is None:
            if not self._engine._mixer_ready:
                self._given_up = True
                return
            self._worker = threading.Thread(target=self._run, daemon=True)
            self._worker.start()
        self._chunks.put(sentence)

    def _run(self) -> None:
        with self._engine._lock:
            while True:
                sentence = self._chunks.get()
                if sentence is None:
                    return
                try:
                    if self._engine.play_one(sentence):
                        self._spoke = True
                except Exception as exc:  # noqa: BLE001 - TTS must never kill the reply
                    logger.warning("EdgeTTS streamed playback failed: %s", exc)
                    self._given_up = True


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

        holder: dict[str, bytes] = {"audio": b""}
        errors: list[BaseException] = []

        def worker() -> None:
            async def run() -> bytes:
                buffer = bytearray()
                communicate = edge_tts.Communicate(text, self.voice)
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        buffer.extend(chunk["data"])
                return bytes(buffer)

            # Own thread with a clean loop: the caller's thread may already have
            # a running asyncio loop (e.g. left by Playwright), which would make
            # run_until_complete raise "Cannot run the event loop while another
            # loop is running".
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                holder["audio"] = loop.run_until_complete(run())
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)
            finally:
                asyncio.set_event_loop(None)
                loop.close()

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        thread.join()
        if errors:
            raise errors[0]
        return holder["audio"]

    def play_one(self, text: str) -> bool:
        """Synthesize and play one sentence, blocking until it finishes."""
        import time

        audio = self._stream(text)
        if not audio:
            return False
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as handle:
            handle.write(audio)
            tmp = Path(handle.name)
        try:
            import pygame  # type: ignore

            pygame.mixer.music.load(str(tmp))
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.05)
        finally:
            import pygame  # type: ignore

            if hasattr(pygame.mixer.music, "unload"):
                pygame.mixer.music.unload()
            tmp.unlink(missing_ok=True)
        return True

    def begin_stream(self) -> SpeechStream:
        return EdgeSpeechStream(self)

    def warmup(self) -> None:
        """Pay the edge-tts TLS handshake before the first real reply needs it."""
        if not self._mixer_ready:
            return
        try:
            self._stream("Ready.")
        except Exception as exc:  # noqa: BLE001 - warmup is best effort
            logger.debug("edge-tts warmup skipped: %s", exc)

    def speak(self, text: str) -> None:
        text = (text or "").strip()
        if not text or not self._mixer_ready:
            return
        try:
            with self._lock:
                self.play_one(text)
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
