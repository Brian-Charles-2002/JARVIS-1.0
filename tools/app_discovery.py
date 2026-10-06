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

# Spoken app name -> likely executable stem (Windows exe names often differ
# from what a user says, e.g. "Edge" -> msedge, "VS Code" -> code).
_NAME_ALIASES: dict[str, list[str]] = {
    "edge": ["msedge"],
    "microsoft edge": ["msedge"],
    "internet explorer": ["iexplore"],
    "chrome": ["chrome"],
    "google chrome": ["chrome"],
    "brave": ["brave"],
    "firefox": ["firefox"],
    "opera": ["opera"],
    "vscode": ["code", "Code"],
    "vs code": ["code", "Code"],
    "visual studio code": ["code", "Code"],
    "word": ["winword"],
    "excel": ["excel"],
    "powerpoint": ["powerpnt"],
    "outlook": ["outlook"],
    "spotify": ["spotify"],
    "discord": ["discord"],
    "terminal": ["wt", "WindowsTerminal"],
    "windows terminal": ["wt", "WindowsTerminal"],
}


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

    # 1) explicit aliases (blank/whitespace values are placeholders: ignore them
    #    and fall through so a template config never hides a real install)
    aliases = user_aliases()
    alias_value = (aliases.get(key) or "").strip()
    if alias_value:
        _discovery_cache[key] = alias_value
        return alias_value

    # 2) well-known commands
    if key in _KNOWN_COMMANDS:
        command = " ".join(_KNOWN_COMMANDS[key])
        _discovery_cache[key] = command
        return command

    # executable-name candidates: the spoken key plus any known exe alias
    seen: set[str] = set()
    candidates: list[str] = []
    for cand in [key, *_NAME_ALIASES.get(key, [])]:
        if cand and cand not in seen:
            seen.add(cand)
            candidates.append(cand)

    # 3) PATH lookup, then 4) registry App Paths, for each exe candidate
    for exe in candidates:
        found = shutil.which(exe) or shutil.which(f"{exe}.exe")
        if found:
            _discovery_cache[key] = found
            return found
        ap = _app_paths(exe)
        if ap and Path(ap).exists():
            _discovery_cache[key] = ap
            return ap

    # 5) Start Menu shortcut name match (spoken name, then exe candidates)
    for probe in [name, *candidates]:
        shortcut = _find_shortcut(probe)
        if shortcut:
            _discovery_cache[key] = str(shortcut)
            return str(shortcut)

    # 6) common install directory scan (exename.exe)
    for base in _COMMON_DIRS:
        if not base.exists():
            continue
        for exe in candidates:
            direct = base / f"{exe}.exe"
            if direct.exists():
                _discovery_cache[key] = str(direct)
                return str(direct)
            one = next(iter(base.glob(f"*/{exe}.exe")), None)
            if one:
                _discovery_cache[key] = str(one)
                return str(one)
            deep = next(iter(base.glob(f"**/{exe}.exe")), None)
            if deep:
                _discovery_cache[key] = str(deep)
                return str(deep)

    return None
