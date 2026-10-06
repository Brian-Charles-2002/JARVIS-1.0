"""Tool package: builds the fully-populated registry used by the agent."""
from __future__ import annotations

from tools.applications import (
    CloseApplication,
    GetRunningApps,
    IsProcessRunning,
    ListProcesses,
    OpenApplication,
)
from tools.base import BaseTool
from tools.browser import OpenBrowser, OpenUrl, ReadPage
from tools.browser_auto import BROWSER_TOOLS
from tools.vision import AnalyzeScreen
from tools.clipboard import GetClipboard, SetClipboard
from tools.filesystem import (
    AppendFile,
    CopyFile,
    CreateFile,
    CreateFolder,
    DeleteFile,
    DeleteFolder,
    FileExists,
    GetFileInfo,
    ListDirectory,
    MoveFile,
    OpenFile,
    ReadFile,
    RenameFile,
    WriteFile,
)
from tools.keyboard_mouse import (
    ClickMouse,
    DoubleClick,
    Hotkey,
    MoveMouse,
    PressKey,
    RightClick,
    Scroll,
    TypeText,
)
from tools.misc import GetCurrentTime, LockComputer, RestartComputer, ShutdownComputer
from tools.registry import ToolRegistry
from tools.screenshots import TakeScreenshot
from tools.system_info import (
    GetBatteryStatus,
    GetCpuUsage,
    GetDiskUsage,
    GetMemoryUsage,
    GetNetworkStatus,
    GetSystemInfo,
)
from tools.terminal import RunTerminalCommand
from tools.web import WebSearch
from tools.windows import FocusWindow, GetActiveWindow, ListWindows

_ALL_TOOLS = [
    # time / info
    GetCurrentTime, GetSystemInfo, GetCpuUsage, GetMemoryUsage, GetDiskUsage,
    GetBatteryStatus, GetNetworkStatus,
    # applications & processes
    OpenApplication, CloseApplication, GetRunningApps, ListProcesses, IsProcessRunning,
    # browser / web
    OpenBrowser, OpenUrl, ReadPage, WebSearch,
    *BROWSER_TOOLS,
    # vision (needs the Gemini client injected below)
    AnalyzeScreen,
    # filesystem
    CreateFolder, CreateFile, WriteFile, AppendFile, ReadFile, ListDirectory,
    CopyFile, MoveFile, RenameFile, OpenFile, FileExists, GetFileInfo,
    DeleteFile, DeleteFolder,
    # keyboard / mouse
    TypeText, PressKey, Hotkey, ClickMouse, DoubleClick, RightClick, MoveMouse, Scroll,
    # clipboard
    GetClipboard, SetClipboard,
    # windows
    GetActiveWindow, ListWindows, FocusWindow,
    # screenshots
    TakeScreenshot,
    # terminal
    RunTerminalCommand,
    # power
    LockComputer, ShutdownComputer, RestartComputer,
]


def build_registry(settings=None, client=None) -> ToolRegistry:
    registry = ToolRegistry()
    for tool_cls in _ALL_TOOLS:
        tool = tool_cls(settings=settings)
        if client is not None and tool.name == "analyze_screen":
            tool.ai_client = client  # type: ignore[attr-defined]
        registry.register(tool)
    return registry


__all__ = ["ToolRegistry", "build_registry"]
