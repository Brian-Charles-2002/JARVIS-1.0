"""Windows application discovery.

Searches PATH, common install directories, the registry App Paths key, and
Start Menu shortcuts. Results are cached. User aliases (from long-term memory or
``app_aliases.json``) are honored first.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from config.settings import PROJECT_ROOT

_COMMON_DIRS = [
    Path(r"C:\Program Files"),
    Path(r"C:\Program Files (x86)"),
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs",
    Path(os.environ.get("APPDATA", "")),
]

_START_MENU_DIRS = [
    Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
    Path(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs"),
]

# Canonical fallbacks for well-known apps so discovery still works offline.
_KNOWN_COMMANDS = {
    "notepad": ["notepad"],
    "calculator": ["calc"],
    "calc": ["calc"],
    "paint": ["mspaint"],
    "cmd": ["cmd"],
    "command prompt": ["cmd"],
    "powershell": ["powershell"],
    "explorer": ["explorer"],
    "file explorer": ["explorer"],
    "settings": ["start", "ms-settings:"],
    "task manager": ["taskmgr"],
}

_alias_cache: dict[str, str] | None = None
_discovery_cache: dict[str, str] = {}


def user_aliases() -> dict[str, str]:
    global _alias_cache
    if _alias_cache is not None:
        return _alias_cache
    path = PROJECT_ROOT / "config" / "app_aliases.json"
    result: dict[str, str] = {}
    if path.exists():
        try:
            result = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            result = {}
    _alias_cache = result
    return result


def _find_shortcut(name: str) -> Path | None:
    target = name.lower()
    for base in _START_MENU_DIRS:
        if not base.exists():
            continue
        for lnk in base.rglob("*.lnk"):
            if lnk.stem.lower() == target:
                return lnk
    return None


def _app_paths(name: str) -> str | None:
    """Query the Windows registry App Paths key for an executable."""
    try:
        import winreg  # type: ignore

        bases = [
            winreg.HKEY_LOCAL_MACHINE,
            winreg.HKEY_CURRENT_USER,
        ]
        subs = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths",
        ]
        exe_variants = {f"{name}.exe", name}
        for hkey in bases:
            for sub in subs:
                try:
                    key = winreg.OpenKey(hkey, sub)
                except OSError:
                    continue
                with key:
                    for i in range(winreg.QueryInfoKey(key)[0]):
                        subkey_name = winreg.EnumKey(key, i)
                        if subkey_name.lower().rstrip(".exe") in {v.lower().rstrip(".exe") for v in exe_variants}:
                            sk = winreg.OpenKey(key, subkey_name)
                            with sk:
                                value, _ = winreg.QueryValueEx(sk, None)
                                return value
    except Exception:  # noqa: BLE001
        return None
    return None


def discover(name: str) -> str | None:
    """Return a launch command/path for an application name, or None."""
    if name is None:
        return None
    key = name.strip().lower()
    if key in _discovery_cache:
        return _discovery_cache[key]

    # 1) explicit aliases
    aliases = user_aliases()
    if key in aliases:
        _discovery_cache[key] = aliases[key]
        return aliases[key]

    # 2) well-known commands
    if key in _KNOWN_COMMANDS:
        command = " ".join(_KNOWN_COMMANDS[key])
        _discovery_cache[key] = command
        return command

    # 3) PATH lookup (e.g. code, chrome, brave)
    found = shutil.which(key) or shutil.which(f"{key}.exe")
    if found:
        _discovery_cache[key] = found
        return found

    # 4) registry App Paths
    ap = _app_paths(key)
    if ap and Path(ap).exists():
        _discovery_cache[key] = ap
        return ap

    # 5) Start Menu shortcut name match
    shortcut = _find_shortcut(name)
    if shortcut:
        _discovery_cache[key] = str(shortcut)
        return str(shortcut)

    # 6) common install directory scan (exename.exe)
    for base in _COMMON_DIRS:
        if not base.exists():
            continue
        candidate = base / f"{key}.exe"
        if candidate.exists():
            _discovery_cache[key] = str(candidate)
            return str(candidate)
        for sub in base.glob(f"*/{key}.exe"):
            _discovery_cache[key] = str(sub)
            return str(sub)
        for sub in base.glob(f"**/{key}.exe"):
            _discovery_cache[key] = str(sub)
            return str(sub)

    return None
