"""Pytest configuration: make the project root importable and provide fixtures.

Unit tests never call the real Gemini API; a fake client is injected where the
agent is exercised.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# A placeholder key so Settings validation passes in tests (never used for calls).
os.environ.setdefault("GEMINI_API_KEY", "test-key-not-real")
os.environ.setdefault("TTS_ENGINE", "none")

import pytest  # noqa: E402

from config.settings import Settings  # noqa: E402


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        assistant_name="Jarvis",
        gemini_api_key="test-key-not-real",
        gemini_model="gemini-test",
        tts_engine="none",
        confirmation_level="DESTRUCTIVE",
        require_confirmation_for_destructive=True,
        data_dir=tmp_path,
        log_dir=tmp_path / "logs",
        project_root=tmp_path,
    )


@pytest.fixture
def tmp_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path
