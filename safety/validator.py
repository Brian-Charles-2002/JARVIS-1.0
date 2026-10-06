"""Pre-execution validation and human-readable action description.

Turns an abstract tool call into a concrete, safe description used by the
confirmation prompt (e.g. counting the items a folder deletion would remove).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.paths import resolve_user_path


def describe_action(tool: str, arguments: dict[str, Any]) -> str:
    """Render a user-facing description of what would happen."""
    if tool in ("delete_file",):
        p = resolve_user_path(arguments.get("path", ""))
        return f"delete the file {p.name} ({p}) and move it to the Recycle Bin"
    if tool in ("delete_folder",):
        p = resolve_user_path(arguments.get("path", ""))
        count = _count_items(p)
        detail = f", which contains {count} items" if count else ""
        return f"delete the folder {p}{detail} (moved to the Recycle Bin if possible)"
    if tool in ("shutdown_computer",):
        return "shut down your computer"
    if tool in ("restart_computer",):
        return "restart your computer (this closes running applications)"
    if tool == "run_terminal_command":
        return f"run this command: {arguments.get('command', '')}"
    if tool == "close_application":
        return f"close the application {arguments.get('name', '')}"
    if tool == "set_clipboard":
        return f"replace your clipboard with: {str(arguments.get('text',''))[:60]!r}"
    if tool == "move_file":
        return f"move {arguments.get('source','')} to {arguments.get('destination','')}"
    if tool == "copy_file":
        return f"copy {arguments.get('source','')} to {arguments.get('destination','')}"
    if tool in ("write_file", "append_file"):
        return f"write to {arguments.get('path','')}"
    if tool == "open_url":
        return f"open {arguments.get('url','')} in your browser"
    if tool == "open_application":
        return f"open {arguments.get('name','')}"
    # generic fallback
    args = ", ".join(f"{k}={v}" for k, v in arguments.items())
    return f"run {tool}({args})"


def _count_items(path: Path) -> int:
    try:
        return sum(1 for _ in path.iterdir())
    except (OSError, ValueError):
        return 0
