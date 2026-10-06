"""Regressions for the tool-call round-trip that previously returned HTTP 400.

Newer Gemini models attach a ``thought_signature`` to function-call parts and
require it back on the following request; and directory listing must never
block the assistant on huge/OneDrive folders.
"""
from google.genai import types

from ai.tool_adapter import to_contents
from core.conversation import ChatMessage, ChatPart
from tools.filesystem import ListDirectory


def _parts(message: ChatMessage):
    return to_contents([message])[0].parts


def test_function_call_echoes_id_and_thought_signature():
    msg = ChatMessage(role="model", parts=[ChatPart(function_call={
        "name": "open_application",
        "args": {"name": "Chrome"},
        "id": "call_1",
        "thought_signature": b"opaque-bytes",
    })])
    part = _parts(msg)[0]
    assert part.function_call.name == "open_application"
    assert part.function_call.id == "call_1"
    assert part.thought_signature == b"opaque-bytes"


def test_function_call_without_signature_still_builds():
    msg = ChatMessage(role="model", parts=[ChatPart(function_call={
        "name": "get_current_time", "args": {}, "id": None, "thought_signature": None,
    })])
    part = _parts(msg)[0]
    assert part.function_call.name == "get_current_time"
    assert getattr(part, "thought_signature", None) is None


def test_function_response_echoes_id():
    msg = ChatMessage(role="user", parts=[ChatPart(function_response={
        "name": "get_current_time", "response": {"success": True}, "id": "call_9",
    })])
    part = _parts(msg)[0]
    assert part.function_response.name == "get_current_time"
    assert part.function_response.id == "call_9"


def test_list_directory_is_bounded_and_fast(tmp_path):
    for i in range(300):
        (tmp_path / f"file_{i}.txt").write_text("x")
    result = ListDirectory().run(str(tmp_path), limit=10)
    payload = result.to_dict()
    assert payload["success"] is True
    assert payload["result"]["count"] == 10
    assert payload["result"]["truncated"] is True


def test_blank_alias_never_returns_empty_string():
    # A placeholder alias ("chrome": "") must not shadow real discovery.
    from tools.app_discovery import discover
    assert discover("chrome") != ""
    assert discover("edge") != ""
    assert discover("no-such-app-xyz-123") is None


class _FakePopen:
    def __init__(self, arg, *a, **k):
        self.arg = arg
        self.shell = k.get("shell", False)

    def poll(self):
        return 0


def test_open_application_spaced_exe_uses_argv(monkeypatch):
    import sys
    import tools.applications as ap

    captured: dict = {}
    real_popen = ap.subprocess.Popen

    def spy(arg, *a, **k):
        proc = _FakePopen(arg, *a, **k)
        captured["arg"] = proc.arg
        captured["shell"] = proc.shell
        return proc

    monkeypatch.setattr(ap.subprocess, "Popen", spy)
    # sys.executable is a real file whose path may contain spaces.
    monkeypatch.setattr(ap, "discover", lambda name: sys.executable)
    ap.OpenApplication().run("anything", "--flag value")
    assert isinstance(captured["arg"], list)
    assert captured["arg"][0] == sys.executable
    assert captured["arg"][1:] == ["--flag", "value"]
    assert captured["shell"] is False
    assert real_popen  # keep reference used for the non-file branch contract


def test_open_application_bare_command_uses_shell(monkeypatch):
    import tools.applications as ap

    captured: dict = {}

    def spy(arg, *a, **k):
        captured["arg"] = arg
        captured["shell"] = k.get("shell", False)
        return _FakePopen(arg, *a, **k)

    monkeypatch.setattr(ap.subprocess, "Popen", spy)
    monkeypatch.setattr(ap, "discover", lambda name: "notepad")
    ap.OpenApplication().run("notepad")
    assert captured["arg"] == "notepad"
    assert captured["shell"] is True

