"""End-to-end latency: speech must begin while Gemini is still generating.

The old pipeline was fully serial, so the user heard nothing until the whole
reply existed. This asserts the first sentence reaches the speaker roughly when
the model finishes writing it, not when it finishes the reply.
"""
import threading
import time

from ai.gemini_client import ModelResponse
from core.agent import Agent
from core.memory import MemoryManager
from tools import build_registry
from voice.text_to_speech import EdgeSpeechStream, EdgeTTS

REPLY = (
    "Paris is the capital of France. "
    "It sits on the river Seine and has about two million residents. "
    "The city is also a major centre for art, fashion and diplomacy."
)
DELTA_GAP = 0.12


class PacedClient:
    """Streams REPLY word by word, sleeping between words like a slow model."""

    def __init__(self):
        self.start = 0.0

    def respond_stream(self, contents, tools, system=None):
        self.start = time.perf_counter()
        for word in REPLY.split(" "):
            yield "delta", word + " "
            time.sleep(DELTA_GAP)
        yield "final", ModelResponse(kind="text", text=REPLY.strip())


def make_stream(plays):
    engine = EdgeTTS.__new__(EdgeTTS)
    engine.voice = "test"
    engine._mixer_ready = True
    engine._lock = threading.Lock()

    def play_one(text):
        plays.append((time.perf_counter(), text))
        return True

    engine.play_one = play_one
    return EdgeSpeechStream(engine)


def test_first_sentence_is_spoken_before_generation_ends(settings):
    plays: list[tuple[float, str]] = []
    stream = make_stream(plays)
    client = PacedClient()
    agent = Agent(settings, client, build_registry(settings), MemoryManager(settings))

    result = agent.handle_text("what is the capital of france?", on_chunk=stream.feed)
    generation_end = time.perf_counter()
    stream.finish()

    assert result.text == REPLY
    assert stream.spoke is True
    first_audio = plays[0][0] - client.start
    total_generation = generation_end - client.start

    assert first_audio < total_generation * 0.6, (
        f"first sentence took {first_audio:.2f}s of a {total_generation:.2f}s reply"
    )
    # the rest still arrives, in order, and finish() waits for all of it
    assert plays[-1][1].endswith("diplomacy.")
    assert " ".join(text for _, text in plays).split() == REPLY.split()
