"""Filesystem tools: create/read/write/list/copy/move/delete, using pathlib.

Deleting uses the Recycle Bin (send2trash) when available and always requires
confirmation because these tools are tagged DESTRUCTIVE.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from safety.risk import RiskLevel
from tools.base import BaseTool, ToolResult
from tools.paths import resolve_user_path


def _info(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path),
        "name": path.name,
        "is_dir": path.is_dir(),
        "is_file": path.is_file(),
        "size_bytes": stat.st_size,
        "modified": stat.st_mtime,
    }


class CreateFolder(BaseTool):
    name = "create_folder"
    description = "Create a new folder (directory) at the given path. Supports 'Desktop/...' style paths."
    risk = RiskLevel.CAUTION
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Folder path, e.g. 'Desktop/AI Projects'"}
        },
        "required": ["path"],
    }

    def run(self, path: str) -> ToolResult:
        target = resolve_user_path(path)
        target.mkdir(parents=True, exist_ok=True)
        if not target.is_dir():
            return ToolResult.fail(self.name, "CREATE_FAILED", f"Could not create folder: {target}")
        return ToolResult.ok(self.name, {"path": str(target), "created": True})


class CreateFile(BaseTool):
    name = "create_file"
    description = "Create an empty file (or one with initial content). Parent folders are created automatically."
    risk = RiskLevel.CAUTION
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path, e.g. 'Desktop/hello.py'"},
            "content": {"type": "string", "description": "Optional initial text content."},
        },
        "required": ["path"],
    }

    def run(self, path: str, content: str = "") -> ToolResult:
        target = resolve_user_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            return ToolResult.fail(self.name, "ALREADY_EXISTS", f"File already exists: {target}")
        target.write_text(content, encoding="utf-8")
        return ToolResult.ok(self.name, {"path": str(target), "bytes": len(content.encode('utf-8'))})


class WriteFile(BaseTool):
    name = "write_file"
    description = "Write (overwrite) text content into a file. Creates the file and parent folders if needed."
    risk = RiskLevel.CAUTION
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["path", "content"],
    }

    def run(self, path: str, content: str) -> ToolResult:
        target = resolve_user_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return ToolResult.ok(self.name, {"path": str(target), "written_bytes": len(content.encode("utf-8"))})


class AppendFile(BaseTool):
    name = "append_file"
    description = "Append text content to the end of a file."
    risk = RiskLevel.CAUTION
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["path", "content"],
    }

    def run(self, path: str, content: str) -> ToolResult:
        target = resolve_user_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(content)
        return ToolResult.ok(self.name, {"path": str(target)})


class ReadFile(BaseTool):
    name = "read_file"
    description = "Read text content from a file. Returns up to max_bytes of content."
    risk = RiskLevel.SAFE
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "max_bytes": {"type": "integer", "description": "Maximum bytes to read (default 20000)."},
        },
        "required": ["path"],
    }

    def run(self, path: str, max_bytes: int = 20000) -> ToolResult:
        target = resolve_user_path(path)
        if not target.is_file():
            return ToolResult.fail(self.name, "FILE_NOT_FOUND", f"No file at {target}")
        try:
            data = target.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            return ToolResult.fail(self.name, "READ_ERROR", str(exc))
        truncated = len(data.encode("utf-8")) > max_bytes
        return ToolResult.ok(self.name, {
            "path": str(target),
            "content": data[:max_bytes],
            "truncated": truncated,
        })


class ListDirectory(BaseTool):
    name = "list_directory"
    description = "List the entries of a directory (name, type, size)."
    risk = RiskLevel.SAFE
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory path, e.g. 'Desktop'"},
            "limit": {"type": "integer", "description": "Max entries to return (default 100)."},
        },
        "required": ["path"],
    }

    def run(self, path: str, limit: int = 100) -> ToolResult:
        target = resolve_user_path(path)
        if not target.is_dir():
            return ToolResult.fail(self.name, "DIR_NOT_FOUND", f"No directory at {target}")
        entries = []
        for child in sorted(target.iterdir()):
            entries.append({
                "name": child.name,
                "is_dir": child.is_dir(),
                "size_bytes": child.stat().st_size if child.is_file() else None,
            })
            if len(entries) >= limit:
                break
        return ToolResult.ok(self.name, {"path": str(target), "count": len(entries), "entries": entries})


class CopyFile(BaseTool):
    name = "copy_file"
    description = "Copy a file or folder to a destination path."
    risk = RiskLevel.CAUTION
    parameters = {
        "type": "object",
        "properties": {"source": {"type": "string"}, "destination": {"type": "string"}},
        "required": ["source", "destination"],
    }

    def run(self, source: str, destination: str) -> ToolResult:
        src, dst = resolve_user_path(source), resolve_user_path(destination)
        if not src.exists():
            return ToolResult.fail(self.name, "SRC_NOT_FOUND", f"Source not found: {src}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)
        return ToolResult.ok(self.name, {"source": str(src), "destination": str(dst)})


class MoveFile(BaseTool):
    name = "move_file"
    description = "Move or rename a file or folder."
    risk = RiskLevel.CAUTION
    parameters = {
        "type": "object",
        "properties": {"source": {"type": "string"}, "destination": {"type": "string"}},
        "required": ["source", "destination"],
    }

    def run(self, source: str, destination: str) -> ToolResult:
        src, dst = resolve_user_path(source), resolve_user_path(destination)
        if not src.exists():
            return ToolResult.fail(self.name, "SRC_NOT_FOUND", f"Source not found: {src}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return ToolResult.ok(self.name, {"from": str(src), "to": str(dst)})


class RenameFile(MoveFile):
    name = "rename_file"
    description = "Rename a file or folder (alias of move within the same directory)."


class OpenFile(BaseTool):
    name = "open_file"
    description = "Open a file or folder with the system default application (equivalent to double-click)."
    risk = RiskLevel.SAFE
    parameters = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    }

    def run(self, path: str) -> ToolResult:
        target = resolve_user_path(path)
        if not target.exists():
            return ToolResult.fail(self.name, "NOT_FOUND", f"Nothing at {target}")
        try:
            os.startfile(str(target))  # type: ignore[attr-defined]  # Windows only
            return ToolResult.ok(self.name, {"path": str(target), "opened": True})
        except Exception as exc:  # noqa: BLE001
            return ToolResult.fail(self.name, "OPEN_FAILED", str(exc))


class FileExists(BaseTool):
    name = "file_exists"
    description = "Check whether a file or folder exists at the given path."
    risk = RiskLevel.SAFE
    parameters = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    }

    def run(self, path: str) -> ToolResult:
        target = resolve_user_path(path)
        return ToolResult.ok(self.name, {"path": str(target), "exists": target.exists()})


class GetFileInfo(BaseTool):
    name = "get_file_info"
    description = "Return metadata about a file or folder (size, modified time, type)."
    risk = RiskLevel.SAFE
    parameters = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    }

    def run(self, path: str) -> ToolResult:
        target = resolve_user_path(path)
        if not target.exists():
            return ToolResult.fail(self.name, "NOT_FOUND", f"Nothing at {target}")
        return ToolResult.ok(self.name, _info(target))


class DeleteFile(BaseTool):
    name = "delete_file"
    description = "Delete a file. Moves it to the Recycle Bin when possible. DESTRUCTIVE - needs confirmation."
    risk = RiskLevel.DESTRUCTIVE
    parameters = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    }

    def run(self, path: str) -> ToolResult:
        target = resolve_user_path(path)
        if not target.is_file():
            return ToolResult.fail(self.name, "FILE_NOT_FOUND", f"No file at {target}")
        try:
            from send2trash import send2trash  # type: ignore

            send2trash(str(target))
            method = "recycle_bin"
        except Exception:  # noqa: BLE001 - fallback to permanent delete
            target.unlink()
            method = "permanent"
        return ToolResult.ok(self.name, {"path": str(target), "deleted": True, "method": method})


class DeleteFolder(BaseTool):
    name = "delete_folder"
    description = "Delete a folder (and its contents). Moves to Recycle Bin when possible. DESTRUCTIVE."
    risk = RiskLevel.DESTRUCTIVE
    parameters = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    }

    def run(self, path: str) -> ToolResult:
        target = resolve_user_path(path)
        if not target.is_dir():
            return ToolResult.fail(self.name, "DIR_NOT_FOUND", f"No directory at {target}")
        try:
            from send2trash import send2trash  # type: ignore

            send2trash(str(target))
            return ToolResult.ok(self.name, {"path": str(target), "deleted": True, "method": "recycle_bin"})
        except Exception:  # noqa: BLE001
            shutil.rmtree(target)
            return ToolResult.ok(self.name, {"path": str(target), "deleted": True, "method": "permanent"})
