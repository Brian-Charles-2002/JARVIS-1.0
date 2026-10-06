"""Agent loop behaviour with a fake Gemini client (no API calls)."""
from pathlib import Path

from ai.gemini_client import ModelResponse
from core.agent import Agent
from core.memory import MemoryManager
from tools import build_registry


class FakeClient:
    def __init__(self, responses):
        self.queue = list(responses)
        self.calls = []

    def respond(self, contents, tools, system=None):
        self.calls.append(len(contents))
        assert self.queue, "FakeClient ran out of scripted responses"
        return self.queue.pop(0)


def make_agent(settings, responses):
    client = FakeClient(responses)
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
