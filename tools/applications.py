"""Application launch/close and running-process tools."""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

import psutil

from safety.risk import RiskLevel
from tools.app_discovery import discover
from tools.base import BaseTool, ToolResult

# Processes that must never be terminated.
_PROTECTED = {
    "system", "smss.exe", "csrss.exe", "wininit.exe", "services.exe",
    "lsass.exe", "svchost.exe", "explorer.exe", "dwm.exe", "winlogon.exe",
    "memory compression", "registry",
}


def _split_args(args: str) -> list[str]:
    """Split an args string into argv tokens, honoring quotes and backslashes."""
    args = (args or "").strip()
    if not args:
        return []
    try:
        import shlex

        tokens = shlex.split(args, posix=False)
    except ValueError:
        tokens = args.split()
    return [t.strip('"') for t in tokens if t]


def _launch(target: str, args: str = "") -> subprocess.Popen:
    """Launch an app detached from JARVIS's own lifecycle.

    A real executable path that contains spaces (``C:\\Program Files\\...``)
    must be passed as its own argv token, not glued into one shell string, or
    ``cmd`` splits it at the first space and fails. Bare commands and the
    ``start``/``ms-settings:`` forms still need a shell.
    """
    tokens = _split_args(args)

    if target.endswith(".lnk"):
        # Open a Start Menu shortcut via Shell
        cmd = ["cmd", "/c", "start", "", target] + tokens
        return subprocess.Popen(cmd, close_fds=True)

    # Existing executable file: launch via argv so Python quotes the path right.
    try:
        is_exe = Path(target).is_file()
    except OSError:
        is_exe = False
    if is_exe:
        return subprocess.Popen([target] + tokens, close_fds=True)

    # Otherwise run through the shell (e.g. "notepad", "calc", "start ms-settings:").
    command = target if not args else f"{target} {args}"
    return subprocess.Popen(command, shell=True, close_fds=True)


class OpenApplication(BaseTool):
    name = "open_application"
    description = "Open a Windows application by name (e.g. Chrome, Notepad, VS Code, Calculator)."
    risk = RiskLevel.SAFE
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Application name or alias."},
            "args": {"type": "string", "description": "Optional command-line arguments or URL/file to open."},
        },
        "required": ["name"],
    }

    def run(self, name: str, args: str = "") -> ToolResult:
        target = discover(name)
        if not target:
            return ToolResult.fail(
                self.name, "APPLICATION_NOT_FOUND",
                f"Could not locate '{name}' installed on this computer.",
            )
        try:
            proc = _launch(target, args)
        except Exception as exc:  # noqa: BLE001
            return ToolResult.fail(self.name, "LAUNCH_FAILED", str(exc))
        # Verify a process is running shortly after launch (best effort).
        time.sleep(0.5)
        alive = proc.poll() is None
        return ToolResult.ok(self.name, {
            "application": name,
            "command": f"{target} {args}".strip(),
            "launched": True,
            "process_alive": alive,
        })


class CloseApplication(BaseTool):
    name = "close_application"
    description = "Close a running application by name. Gracefully requests windows to close."
    risk = RiskLevel.CAUTION
    parameters = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    }

    def run(self, name: str) -> ToolResult:
        exe = name.lower()
        if not exe.endswith(".exe"):
            exe_name = f"{exe}.exe"
        else:
            exe_name = exe
        if exe_name in _PROTECTED:
            return ToolResult.fail(self.name, "PROTECTED_PROCESS", f"Refusing to close '{name}'.")
        matched = [p for p in psutil.process_iter(["name"])
                   if (p.info["name"] or "").lower() == exe_name]
        if not matched:
            return ToolResult.fail(self.name, "NOT_RUNNING", f"'{name}' does not appear to be running.")
        closed = 0
        for proc in matched:
            try:
                proc.terminate()
                closed += 1
            except psutil.Error:
                pass
        return ToolResult.ok(self.name, {"application": name, "instances_closed": closed})


class GetRunningApps(BaseTool):
    name = "get_running_apps"
    description = "List running desktop applications (processes with a window) and their names."
    risk = RiskLevel.SAFE
    parameters = {"type": "object", "properties": {"limit": {"type": "integer"}}}

    def run(self, limit: int = 40) -> ToolResult:
        apps = []
        seen = set()
        for proc in psutil.process_iter(["name", "pid"]):
            name = proc.info["name"] or ""
            if not name.endswith(".exe"):
                continue
            low = name.lower()
            if low in seen:
                continue
            # only report common GUI-ish apps to reduce noise
            if low in _PROTECTED or low in {"svchost.exe", "runtimebroker.exe", "searchhost.exe"}:
                continue
            seen.add(low)
            apps.append({"name": name, "pid": proc.info["pid"]})
            if len(apps) >= limit:
                break
        return ToolResult.ok(self.name, {"count": len(apps), "apps": sorted(apps, key=lambda a: a["name"])})


class ListProcesses(BaseTool):
    name = "list_processes"
    description = "List running processes with pid and name. DESTRUCTIVE tools should not use this to force-kill."
    risk = RiskLevel.SAFE
    parameters = {
        "type": "object",
        "properties": {"filter": {"type": "string"}, "limit": {"type": "integer"}},
    }

    def run(self, filter: str = "", limit: int = 100) -> ToolResult:
        results = []
        needle = filter.lower()
        for proc in psutil.process_iter(["name", "pid"]):
            name = (proc.info["name"] or "")
            if needle and needle not in name.lower():
                continue
            results.append({"name": name, "pid": proc.info["pid"]})
            if len(results) >= limit:
                break
        return ToolResult.ok(self.name, {"count": len(results), "processes": results})


class IsProcessRunning(BaseTool):
    name = "is_process_running"
    description = "Check whether a process (by executable name, e.g. 'chrome.exe') is currently running."
    risk = RiskLevel.SAFE
    parameters = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
    }

    def run(self, name: str) -> ToolResult:
        exe = name.lower()
        if not exe.endswith(".exe"):
            exe = f"{exe}.exe"
        count = sum(1 for p in psutil.process_iter(["name"]) if (p.info["name"] or "").lower() == exe)
        return ToolResult.ok(self.name, {"name": name, "running": count > 0, "instances": count})
