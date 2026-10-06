"""Configuration loading and validation."""
from config.settings import ConfigError, Settings, validate_settings


def test_defaults_are_sane():
    s = Settings()
    assert s.assistant_name == "Jarvis"
    assert s.gemini_model  # has a default
    assert s.confirmation_level == "DESTRUCTIVE"


def test_validate_requires_key():
    s = Settings(gemini_api_key="")
    try:
        validate_settings(s)
        assert False, "should have raised"
    except ConfigError as exc:
        assert "GEMINI_API_KEY" in str(exc)


def test_validate_rejects_bad_confirmation_level():
    s = Settings(gemini_api_key="x", confirmation_level="NOPE")
    try:
        validate_settings(s)
        assert False
    except ConfigError:
        pass


def test_validate_passes_with_key():
    s = Settings(gemini_api_key="x", confirmation_level="SAFE")
    validate_settings(s)
