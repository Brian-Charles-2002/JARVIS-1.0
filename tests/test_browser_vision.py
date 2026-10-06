"""Browser-automation and vision tools: registration, schemas, risk wiring.

These tests check structure only - they never launch Chromium or capture the
screen, so they are safe for headless/CI environments.
"""
from safety.risk import RiskLevel
from tools import build_registry
from tools.browser_auto import BrowserType, BROWSER_TOOLS
from tools.vision import AnalyzeScreen


def test_registry_includes_new_browser_and_vision_tools(settings):
    registry = build_registry(settings)
    for name in ("browser_navigate", "browser_get_links", "browser_click",
                 "browser_state", "analyze_screen"):
        assert name in registry


def test_new_tools_have_gemini_schemas(settings):
    registry = build_registry(settings)
    schemas = {s["name"]: s for s in registry.schemas()}
    assert schemas["browser_navigate"]["parameters"]["required"] == ["url"]
    assert "instruction" in schemas["analyze_screen"]["parameters"]["properties"]


def test_all_browser_tools_registered(settings):
    registry = build_registry(settings)
    assert all(tool.name in registry for tool in BROWSER_TOOLS)


def test_vision_tool_risk_is_safe():
    assert AnalyzeScreen().risk == RiskLevel.SAFE


def test_analyze_screen_without_client_fails_gracefully():
    tool = AnalyzeScreen()
    result = tool.invoke({"instruction": "what's on screen?"})
    assert result.success is False
    assert result.error["type"] == "NO_AI_CLIENT"


def test_ai_client_is_injected_into_vision_tool(settings):
    class _FakeClient:
        def analyze_image(self, path, instruction):
            return "a fake analysis"

    registry = build_registry(settings, client=_FakeClient())
    vision = registry.get("analyze_screen")
    assert getattr(vision, "ai_client", None) is not None


def test_browser_type_submit_is_sensitive():
    tool = BrowserType()
    assert tool.risk_for({"submit": True}) == RiskLevel.SENSITIVE
    assert tool.risk_for({"submit": False}) == RiskLevel.CAUTION


def test_short_term_tracks_browser_state():
    from memory.short_term import ShortTermMemory
    from tools.base import ToolResult

    m = ShortTermMemory()
    m.note_result("browser_navigate", {"url": "https://youtube.com"},
                  ToolResult.ok("browser_navigate", {"url": "https://youtube.com", "title": "YouTube"}))
    assert m.last_url == "https://youtube.com"
    assert m.active_browser == "playwright"
