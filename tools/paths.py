"""Robust Windows path resolution.

Desktop/Documents may live under OneDrive or be redirected via known-folder
locations, so ``Path.home() / "Desktop"`` is not reliable. We query the Windows
Shell API when available and fall back gracefully.
"""
from __future__ import annotations

import os
from pathlib import Path

# Human-friendly tokens a user/Gemini may reference.
_ALIASES = {
    "desktop": "Desktop",
    "documents": "Documents",
    "downloads": "Downloads",
    "pictures": "Pictures",
    "videos": "Videos",
    "music": "Music",
    "home": "",
    "appdata": "AppData/Roaming",
}

_KNOWN_FOLDER_GUIDS = {
    "Desktop": "{B4BF3C89-301C-4388-BBBE-7BE4A0D755F2}",
    "Documents": "{FDD39AD0-747C-49A4-BBFB-A67F4A91E7D2}",
    "Downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
    "Pictures": "{33E28130-4E9E-4C81-B300-504F0C4FA2F3}",
    "Videos": "{18989B1D-99B5-455B-841C-AB7C4C74E4DD}",
    "Music": "{4BD8D571-6D19-48D3-BE97-422220080E43}",
}

_cache: dict[str, Path] = {}


def _win_known_folder(name: str) -> Path | None:
    try:
        import ctypes
        from ctypes import wintypes

        class _GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_byte * 8),
            ]

        def _guid(text: str) -> _GUID:
            text = text.strip("{}")
            d1, d2, d3, rest = text[:8], text[9:13], text[14:18], text[19:]
            b1, b2, b3, b4, b5, b6, b7, b8 = (
                int(rest[0:2], 16), int(rest[2:4], 16), int(rest[4:6], 16),
                int(rest[6:8], 16), int(rest[9:11], 16), int(rest[11:13], 16),
                int(rest[13:15], 16), int(rest[15:17], 16),
            )
            g = _GUID()
            g.Data1 = int(d1, 16)
            g.Data2 = int(d2, 16)
            g.Data3 = int(d3, 16)
            g.Data4 = (ctypes.c_byte * 8)(b1, b2, b3, b4, b5, b6, b7, b8)
            return g

        shell32 = ctypes.windll.shell32
        ole32 = ctypes.windll.ole32
        path_ptr = ctypes.c_wchar_p()
        hr = shell32.SHGetKnownFolderPath(ctypes.byref(_guid(_KNOWN_FOLDER_GUIDS[name])), 0, 0, ctypes.byref(path_ptr))
        if hr == 0 and path_ptr.value:
            return Path(path_ptr.value)
        ole32.CoTaskMemFree(ctypes.byref(path_ptr))
    except Exception:  # noqa: BLE001 - any failure just means "no known folder"
        return None
    return None


def known_folder(name: str) -> Path:
    """Return a Windows known folder (Desktop, Documents, ...) reliably."""
    canonical = _ALIASES.get(name.lower(), name)
    if canonical in _cache:
        return _cache[canonical]
    result: Path | None = None
    if canonical in _KNOWN_FOLDER_GUIDS:
        result = _win_known_folder(canonical)
    if result is None or not result.exists():
        fallback = Path.home() / canonical if canonical else Path.home()
        result = fallback
    _cache[canonical] = result
    return result


def resolve_user_path(raw: str | os.PathLike[str]) -> Path:
    """Resolve a user-facing path to an absolute, expanded ``Path``.

    Accepts tokens like ``Desktop/notes.txt``, ``~/file`` and plain paths.
    """
    text = str(raw).strip().strip('"').strip("'")
    if not text:
        return Path.home()
    expanded = Path(os.path.expanduser(text))
    if expanded.is_absolute():
        return expanded

    # leading token may be a known-folder alias: "desktop/AI Projects/x"
    parts = text.replace("\\", "/").split("/")
    first = parts[0].lower()
    if first in _ALIASES:
        base = known_folder(parts[0])
        rest = parts[1:]
        return base.joinpath(*rest) if rest else base

    # otherwise relative to home
    return Path.home() / expanded


def within_user_home(path: Path) -> bool:
    """True when ``path`` is under the user home directory."""
    try:
        path.resolve().relative_to(Path.home().resolve())
        return True
    except (ValueError, OSError):
        return False
