"""The Brain must emit UI events (used by the desktop overlay).

These exercise the new ``on_event`` contract without touching the network or a
display: a bare Brain is wired with just enough state to call ``_respond`` and
``process``'s quick paths.
"""
from core.brain import Brain


def _bare_brain() -> tuple[Brain, list[dict]]:
    brain = Brain.__new__(Brain)
    events: list[dict] = []
    brain.on_event = events.append

    class _Settings:
        assistant_name = "jarvis"

    brain.settings = _Settings()
    brain.speak = lambda text: None  # never actually synthesise
    return brain, events


def test_respond_emits_reply_and_state(monkeypatch):
    brain, events = _bare_brain()
    monkeypatch.setattr("builtins.print", lambda *a, **k: None)
    brain._respond("Hello there.", speak=True)
    kinds = [(e["type"], e.get("state") or e.get("text")) for e in events]
    assert ("reply", "Hello there.") in kinds
    assert ("state", "speaking") in kinds
    assert ("state", "idle") in kinds


def test_process_cancel_and_status_emit_user(monkeypatch):
    brain, events = _bare_brain()
    monkeypatch.setattr("builtins.print", lambda *a, **k: None)
    brain.agent = type("A", (), {"cancel": lambda self: None, "task": None})()
    reply, keep = brain.process("cancel")
    assert keep is True
    assert any(e["type"] == "user" and e["text"] == "cancel" for e in events)
    assert any(e["type"] == "reply" for e in events)


class _FakeStream:
    def __init__(self):
        self.fed: list[str] = []
        self.finished = False
        self._spoke = False

    def feed(self, delta):
        self.fed.append(delta)
        self._spoke = True

    def finish(self):
        self.finished = True

    @property
    def spoke(self):
        return self._spoke


class _FakeTTS:
    def __init__(self, stream):
        self.stream = stream
        self.spoken: list[str] = []

    def begin_stream(self):
        return self.stream

    def speak(self, text):
        self.spoken.append(text)


class _FakeAgent:
    """Streams the given deltas, then returns the finished reply."""

    task = None

    def __init__(self, reply, deltas=()):
        self.reply = reply
        self.deltas = list(deltas)

    def handle_text(self, text, token=None, on_chunk=None):
        from core.agent import AgentResult

        if on_chunk:
            for delta in self.deltas:
                on_chunk(delta)
        return AgentResult(self.reply)


def _speaking_brain(monkeypatch, reply, deltas):
    brain, events = _bare_brain()
    monkeypatch.setattr("builtins.print", lambda *a, **k: None)
    stream = _FakeStream()
    brain.tts = _FakeTTS(stream)
    del brain.speak  # use the real self.speak -> brain.tts.speak
    brain.token = None
    brain.agent = _FakeAgent(reply, deltas)
    return brain, events, stream


def test_streamed_reply_speaks_once_through_the_stream(monkeypatch):
    brain, events, stream = _speaking_brain(
        monkeypatch, "Paris is the capital of France.", ["Paris is the ", "capital of France."]
    )
    reply, keep = brain.process("capital of france?")
    assert keep and reply == "Paris is the capital of France."
    assert stream.fed == ["Paris is the ", "capital of France."]
    assert stream.finished is True
    assert brain.tts.spoken == [], "must not re-speak what the stream already said"
    assert any(e == {"type": "state", "state": "speaking"} for e in events)


def test_locally_generated_reply_falls_back_to_speak(monkeypatch):
    """Confirmation prompts and step limits never reach the model's deltas."""
    brain, _, stream = _speaking_brain(monkeypatch, "Should I continue?", [])
    brain.process("delete everything")
    assert stream.finished is True
    assert brain.tts.spoken == ["Should I continue?"]
