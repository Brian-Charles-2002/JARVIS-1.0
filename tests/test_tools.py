"""Tool registry, filesystem tools, schema and validation behaviour."""
from pathlib import Path

from safety.risk import RiskLevel
from tools import build_registry
from tools.base import ToolCall, ToolResult
from tools.filesystem import CreateFolder, CreateFile, WriteFile, ReadFile, ListDirectory, DeleteFile
from tools.registry import ToolRegistry
from tools.misc import GetCurrentTime


def test_registry_has_core_tools(settings):
    registry = build_registry(settings)
    for name in ("open_application", "create_folder", "read_file", "get_system_info",
                 "web_search", "run_terminal_command", "get_current_time"):
        assert name in registry


def test_registry_schemas_are_gemini_ready(settings):
    schemas = build_registry(settings).schemas()
    assert schemas and all({"name", "description", "parameters"} <= set(s) for s in schemas)


def test_unknown_tool_returns_failure(settings):
    registry = build_registry(settings)
    result = registry.call(ToolCall(name="does_not_exist", arguments={}))
    assert result.success is False
    assert result.error["type"] == "UNKNOWN_TOOL"


def test_missing_required_argument_is_validated():
    tool = CreateFile()
    result = tool.invoke({})  # no path
    assert result.success is False
    assert result.error["type"] == "INVALID_ARGUMENTS"


def test_wrong_argument_type_is_validated():
    tool = ListDirectory()
    result = tool.invoke({"path": 123})
    assert result.success is False
    assert result.error["type"] == "INVALID_ARGUMENTS"


def test_create_folder_and_file_and_read(tmp_path: Path):
    folder = tmp_path / "Jarvis Test"
    res = CreateFolder().run(path=str(folder))
    assert res.success and folder.is_dir()

    file = folder / "hello.py"
    res = CreateFile().run(path=str(file), content="print('hi')")
    assert res.success and file.is_file()

    res = WriteFile().run(path=str(file), content="print('Hello, World!')")
    assert res.success

    res = ReadFile().run(path=str(file))
    assert res.success and "Hello, World!" in res.result["content"]


def test_list_directory(tmp_path: Path):
    (tmp_path / "a.txt").write_text("a")
    res = ListDirectory().run(path=str(tmp_path))
    assert res.success and any(e["name"] == "a.txt" for e in res.result["entries"])


def test_delete_file_is_destructive(tmp_path: Path):
    assert DeleteFile().risk == RiskLevel.DESTRUCTIVE
    f = tmp_path / "x.txt"
    f.write_text("x")
    res = DeleteFile().run(path=str(f))
    assert res.success and not f.exists()


def test_tool_result_serialization_shape():
    result = ToolResult.ok("create_folder", {"path": "C:/x"})
    payload = result.to_dict()
    assert payload["success"] is True
    assert payload["tool"] == "create_folder"
    assert payload["error"] is None


def test_get_current_time_has_greeting():
    result = GetCurrentTime().run()
    assert result.success and "greeting" in result.result
