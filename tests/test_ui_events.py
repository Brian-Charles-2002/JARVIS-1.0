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
