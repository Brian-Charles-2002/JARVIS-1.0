"""Controlled terminal execution with timeouts and risk classification.

The command itself is proposed by Gemini but NEVER trusted: risk is computed
locally (see safety/risk.py) and enforced by the permission layer before this
handler ever runs.
"""
from __future__ import annotations

import subprocess
import time

from safety.risk import RiskLevel, classify_command
from tools.base import BaseTool, ToolResult


class RunTerminalCommand(BaseTool):
    name = "run_terminal_command"
    description = (
        "Run a single shell command and return stdout, stderr, exit code and timing. "
        "Use for safe tasks like checking versions or listing files. Dangerous "
        "commands are blocked pending user confirmation."
    )
    risk = RiskLevel.CAUTION
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The command to execute."},
            "cwd": {"type": "string", "description": "Optional working directory."},
            "timeout_seconds": {"type": "integer", "description": "Max runtime (default 60)."},
        },
        "required": ["command"],
    }

    def risk_for(self, arguments: dict) -> RiskLevel:
        return classify_command(arguments.get("command", ""))

    def run(self, command: str, cwd: str = "", timeout_seconds: int = 60) -> ToolResult:
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                command,
                shell=True,
                cwd=cwd or None,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired:
            return ToolResult.fail(self.name, "TIMEOUT", f"Command exceeded {timeout_seconds}s.")
        except Exception as exc:  # noqa: BLE001
            return ToolResult.fail(self.name, "EXEC_ERROR", str(exc))
        elapsed = round((time.perf_counter() - started) * 1000, 1)
        max_out = 8000
        return ToolResult.ok(self.name, {
            "command": command,
            "stdout": completed.stdout[:max_out],
            "stderr": completed.stderr[:max_out],
            "exit_code": completed.returncode,
            "execution_time_ms": elapsed,
        })
