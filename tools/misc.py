"""Misc + power tools.

Power actions (shutdown/restart/sleep/lock) are DESTRUCTIVE/SENSITIVE and the
permission layer will require explicit confirmation before they execute.
"""
from __future__ import annotations

import subprocess
from datetime import datetime

from safety.risk import RiskLevel
from tools.base import BaseTool, ToolResult


class GetCurrentTime(BaseTool):
    name = "get_current_time"
    description = "Return the current local date and time."
    risk = RiskLevel.SAFE
    parameters = {"type": "object", "properties": {}}

    def run(self) -> ToolResult:
        now = datetime.now().astimezone()
        return ToolResult.ok(self.name, {
            "iso": now.isoformat(timespec="seconds"),
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M"),
            "weekday": now.strftime("%A"),
            "greeting": _greeting(now.hour),
        })


def _greeting(hour: int) -> str:
    if 5 <= hour < 12:
        return "Good morning"
    if 12 <= hour < 18:
        return "Good afternoon"
    return "Good evening"


class LockComputer(BaseTool):
    name = "lock_computer"
    description = "Lock the current Windows session."
    risk = RiskLevel.SENSITIVE
    parameters = {"type": "object", "properties": {}}

    def run(self) -> ToolResult:
        try:
            subprocess.run("rundll32.exe user32.dll,LockWorkStation", shell=True, check=False, timeout=10)
            return ToolResult.ok(self.name, {"locked": True})
        except Exception as exc:  # noqa: BLE001
            return ToolResult.fail(self.name, "LOCK_FAILED", str(exc))


class _PowerTool(BaseTool):
    command: str = ""

    def run(self, delay_seconds: int = 5) -> ToolResult:
        try:
            subprocess.Popen(f"shutdown {self.command} /t {int(delay_seconds)}", shell=True)
            return ToolResult.ok(self.name, {"scheduled": True, "delay_seconds": delay_seconds})
        except Exception as exc:  # noqa: BLE001
            return ToolResult.fail(self.name, "POWER_FAILED", str(exc))


class ShutdownComputer(_PowerTool):
    name = "shutdown_computer"
    description = "Shut down the computer. DESTRUCTIVE - always requires confirmation."
    risk = RiskLevel.DESTRUCTIVE
    command = "/s"
    parameters = {"type": "object", "properties": {"delay_seconds": {"type": "integer"}}}


class RestartComputer(_PowerTool):
    name = "restart_computer"
    description = "Restart the computer. DESTRUCTIVE - always requires confirmation."
    risk = RiskLevel.DESTRUCTIVE
    command = "/r"
    parameters = {"type": "object", "properties": {"delay_seconds": {"type": "integer"}}}
