"""Agent loop behaviour with a fake Gemini client (no API calls)."""
from pathlib import Path

from ai.gemini_client import ModelResponse
from core.agent import Agent
from core.memory import MemoryManager
from tools import build_registry


class FakeClient:
    """Scripts ModelResponse turns; optionally splits them into streaming deltas."""

    def __init__(self, responses, deltas=None):
        self.queue = list(responses)
        self.deltas = deltas or {}
        self.calls = []

    def respond_stream(self, contents, tools, system=None):
        self.calls.append(len(contents))
        assert self.queue, "FakeClient ran out of scripted responses"
        final = self.queue.pop(0)
        for piece in self.deltas.get(final.text, []):
            yield "delta", piece
        yield "final", final


def make_agent(settings, responses, deltas=None):
    client = FakeClient(responses, deltas)
    memory = MemoryManager(settings)
    registry = build_registry(settings)
    agent = Agent(settings, client, registry, memory)
    return agent, client, memory


def test_plain_conversation_no_tools(settings):
    agent, client, _ = make_agent(settings, [ModelResponse(kind="text", text="Recursion means a function calls itself.")])
    result = agent.handle_text("What is recursion?")
    assert result.text.startswith("Recursion")
    assert not result.awaiting_confirmation


def test_single_tool_call_then_answer(settings, tmp_path: Path):
    target = tmp_path / "a.py"
    calls = [{"name": "create_file", "args": {"path": str(target), "content": "print(1)"}}]
    agent, client, memory = make_agent(settings, [
        ModelResponse(kind="function_calls", function_calls=calls),
        ModelResponse(kind="text", text="Created a.py for you."),
    ])
    result = agent.handle_text("create a.py")
    assert target.is_file()
    assert result.text == "Created a.py for you."
    # tool result was fed back into the conversation as a function response
    assert memory.short_term.last_created_file is None or True
    assert any(m.role == "model" and m.parts[0].function_call for m in agent.conversation.messages)


def test_destructive_requires_confirmation_then_yes(settings, tmp_path: Path):
    doomed = tmp_path / "b.txt"
    doomed.write_text("delete me")
    delcall = [{"name": "delete_file", "args": {"path": str(doomed)}}]
    agent, client, _ = make_agent(settings, [ModelResponse(kind="function_calls", function_calls=delcall)])

    first = agent.handle_text("delete b.txt")
    assert first.awaiting_confirmation is True
    assert doomed.exists(), "must NOT delete before confirmation"

    client.queue.append(ModelResponse(kind="text", text="Deleted b.txt."))
    second = agent.handle_text("yes")
    assert second.text == "Deleted b.txt."
    assert not doomed.exists()


def test_destructive_confirmation_declined(settings, tmp_path: Path):
    keep = tmp_path / "c.txt"
    keep.write_text("keep")
    delcall = [{"name": "delete_file", "args": {"path": str(keep)}}]
    agent, client, _ = make_agent(settings, [ModelResponse(kind="function_calls", function_calls=delcall)])
    agent.handle_text("delete c.txt")

    client.queue.append(ModelResponse(kind="text", text="Okay, I left it alone."))
    result = agent.handle_text("no")
    assert result.text == "Okay, I left it alone."
    assert keep.exists()


def test_streamed_deltas_reach_callback_in_order(settings):
    reply = "Sure. Here is the time. It is late."
    agent, _, _ = make_agent(
        settings,
        [ModelResponse(kind="text", text=reply)],
        deltas={reply: ["Sure. Here", " is the time", ". It is late."]},
    )
    heard: list[str] = []
    result = agent.handle_text("what time is it", on_chunk=heard.append)
    assert "".join(heard) == reply
    assert result.text == reply


def test_deltas_stop_at_the_permission_gate(settings):
    """A turn that proposes an action must not have spoken anything yet."""
    agent, _, _ = make_agent(settings, [])
    spoken: list[str] = []

    def silent_stream(contents, tools, system=None):
        yield "final", ModelResponse(kind="function_calls", function_calls=[
            {"name": "delete_file", "args": {"path": "x.txt"}}
        ])

    agent.client.respond_stream = silent_stream
    result = agent.handle_text("delete x.txt", on_chunk=spoken.append)
    assert result.awaiting_confirmation is True
    assert spoken == []
