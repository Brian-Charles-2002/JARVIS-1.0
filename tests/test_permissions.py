"""Permission classification and terminal command risk."""
from safety.risk import RiskLevel, classify_command
from tools import build_registry
from core.permissions import PermissionManager


def test_destructive_tool_requires_confirmation(settings):
    # default confirmation_level is already DESTRUCTIVE
    registry = build_registry(settings)
    perms = PermissionManager(settings, registry)
    assert perms.needs_confirmation("delete_file", {"path": "C:/x/y.txt"}) is True
    assert perms.needs_confirmation("open_application", {"name": "Notepad"}) is False


def test_safe_tool_never_confirms(settings):
    registry = build_registry(settings)
    perms = PermissionManager(settings, registry)
    assert perms.needs_confirmation("get_system_info", {}) is False
    assert perms.needs_confirmation("read_file", {"path": "C:/x"}) is False


def test_dangerous_terminal_command_is_destructive(settings):
    registry = build_registry(settings)
    perms = PermissionManager(settings, registry)
    assert perms.needs_confirmation(
        "run_terminal_command", {"command": "del /f /s /q C:\\Windows"}
    ) is True


def test_benign_terminal_command_is_caution(settings):
    # default threshold is DESTRUCTIVE so a CAUTION command should NOT confirm
    registry = build_registry(settings)
    perms = PermissionManager(settings, registry)
    assert perms.needs_confirmation(
        "run_terminal_command", {"command": "python --version"}
    ) is False


def test_classify_command_levels():
    assert classify_command("shutdown /s /t 0") == RiskLevel.DESTRUCTIVE
    assert classify_command("reg delete HKLM\\Foo") == RiskLevel.DESTRUCTIVE
    assert classify_command("ipconfig") == RiskLevel.SAFE
    assert classify_command("python script.py") == RiskLevel.CAUTION


def test_pending_action_has_description(settings):
    registry = build_registry(settings)
    perms = PermissionManager(settings, registry)
    pending = perms.build_pending("delete_folder", {"path": "C:/nope"}, call_id="1")
    assert pending.risk == RiskLevel.DESTRUCTIVE
    assert "folder" in pending.description.lower()
