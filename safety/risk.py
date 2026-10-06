"""Risk classification shared by tools, permissions and the confirmation system."""
from __future__ import annotations

import re
from enum import IntEnum


class RiskLevel(IntEnum):
    """Ordered risk levels. Higher value == more dangerous."""

    SAFE = 0
    CAUTION = 1
    SENSITIVE = 2
    DESTRUCTIVE = 3

    @classmethod
    def parse(cls, value: str) -> "RiskLevel":
        return cls[value.strip().upper()]


# Command fragments that indicate a potentially destructive / dangerous
# terminal action. Matched case-insensitively against the whole command.
DANGEROUS_COMMAND_PATTERNS: list[str] = [
    r"\brm\s+-rf\b",
    r"\bdel\s+/[fsq]\b",
    r"\brd\s+/s\b",
    r"\brmdir\s+/s\b",
    r"\bformat\b",
    r"\bmkfs\b",
    r"\bdiskpart\b",
    r"\bcdll\s+/s\b",
    r"\bdism\s+.*cleanup",
    r"bcdedit\b",
    r"\breg\s+delete\b",
    r"vssadmin\s+delete",
    r"\bnet\s+sh\s+del\b",
    r"Remove-Item\s+.*-Recurse",
    r"\bDel\b.*-Recurse",
    r"Set-MpPreference.*Disable",
    r"Set-NetFirewall",
    r"New-NetFirewallRule",
    r"net\s+user\s+/del",
    r"Netplwiz",
    r"\bshutdown\b",
    r"\brestart\b",
    r"Restart-Computer",
    r"Stop-Computer",
    r"\biex(e|plorer)?\b.*https?://",
    r"Invoke-WebRequest.*\|\s*(iex|Invoke-Expression)",
    r"\bcurl\b.*\|\s*(ba)?sh",
    r"wmic\s+.*delete",
    r"taskkill\s+/f",
    r"certutil.*decode",
    r"\bmkfs\.",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in DANGEROUS_COMMAND_PATTERNS]

# Terminal commands that are considered safe read-only information queries.
SAFE_COMMAND_PREFIXES: list[str] = [
    "echo", "whoami", "hostname", "ver", "date", "time", "dir", "ls",
    "type ", "get-content", "systeminfo", "ipconfig", "ping", "tracert",
    "python --version", "python -v", "pip list", "pip show", "where",
    "which", "cat", "head", "tail", "df", "free",
]


def classify_command(command: str) -> RiskLevel:
    """Classify a raw shell command's risk level."""
    cmd = command.strip()
    if any(pattern.search(cmd) for pattern in _COMPILED):
        return RiskLevel.DESTRUCTIVE
    lowered = cmd.lower()
    if any(lowered.startswith(prefix.strip().lower()) for prefix in SAFE_COMMAND_PREFIXES):
        return RiskLevel.SAFE
    return RiskLevel.CAUTION


def requires_confirmation(level: RiskLevel, threshold: RiskLevel, destructive_flag: bool) -> bool:
    """Decide whether an action at ``level`` needs user confirmation."""
    if level >= threshold:
        return True
    if level == RiskLevel.DESTRUCTIVE and destructive_flag:
        return True
    return False
