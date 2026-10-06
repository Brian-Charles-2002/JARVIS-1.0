"""Session + persistent memory behaviour and reference tracking."""
from tools.base import ToolResult
from memory.short_term import ShortTermMemory
from memory.long_term import LongTermMemory


def test_short_term_tracks_created_folder_and_file():
    m = ShortTermMemory()
    m.note_result("create_folder", {"path": "C:/Desktop/AI Projects"},
                  ToolResult.ok("create_folder", {"path": "C:/Desktop/AI Projects"}))
    assert m.last_created_folder == "C:/Desktop/AI Projects"

    m.note_result("create_file", {"path": "C:/Desktop/AI Projects/hello.py"},
                  ToolResult.ok("create_file", {"path": "C:/Desktop/AI Projects/hello.py"}))
    assert m.last_created_file.endswith("hello.py")

    ctx = m.to_context_dict()
    assert "last_created_folder" in ctx and "last_created_file" in ctx


def test_short_term_tracks_search_and_browser():
    m = ShortTermMemory()
    m.note_result("open_url", {"url": "youtube.com"},
                  ToolResult.ok("open_url", {"url": "https://youtube.com", "browser": "chrome"}))
    assert m.last_url == "https://youtube.com"
    assert m.active_browser == "chrome"
    m.note_result("web_search", {"query": "python tutorials"},
                  ToolResult.ok("web_search", {"query": "python tutorials", "results": []}))
    assert m.last_search_query == "python tutorials"


def test_failed_result_does_not_pollute_state():
    m = ShortTermMemory()
    m.note_result("create_file", {"path": "x"},
                  ToolResult.fail("create_file", "ERR", "boom"))
    assert m.last_created_file is None


def test_long_term_persists_preferences(settings):
    lt = LongTermMemory(settings.data_dir / "mem.db")
    lt.set("preferred_browser", "chrome")
    assert lt.get("preferred_browser") == "chrome"
    lt.close()


def test_long_term_refuses_secrets(settings):
    lt = LongTermMemory(settings.data_dir / "mem.db")
    lt.set("gmail_password", "hunter2")
    lt.set("note", "my api_key=AIza1234567890abcdefgh")
    assert lt.get("gmail_password") is None
    assert lt.get("note") is None
    lt.close()
