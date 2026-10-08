"""The CLI brain finds `claude` even when launched with a minimal PATH (Claude Desktop, cron, systemd)."""

import importlib

import pytest

# the module, not the `brain()` function that engine.core re-exports under the same name
brain = importlib.import_module("engine.core.brain")


def _exe(tmp_path, name="claude"):
    p = tmp_path / name
    p.write_text("#!/bin/sh\n")
    p.chmod(0o755)
    return p


def test_explicit_env_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("ENGINE_CLAUDE_BIN", str(_exe(tmp_path, "my-claude")))
    assert brain._claude_bin() == str(tmp_path / "my-claude")


def test_falls_back_to_standard_install_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("ENGINE_CLAUDE_BIN", raising=False)
    monkeypatch.setenv("PATH", "/nonexistent")
    monkeypatch.setattr(brain, "_CLAUDE_FALLBACKS", (str(_exe(tmp_path)),))
    assert brain._claude_bin() == str(tmp_path / "claude")


def test_not_found_names_the_fix(monkeypatch):
    monkeypatch.delenv("ENGINE_CLAUDE_BIN", raising=False)
    monkeypatch.setenv("PATH", "/nonexistent")
    monkeypatch.setattr(brain, "_CLAUDE_FALLBACKS", ("/nonexistent/claude",))
    with pytest.raises(brain.BrainError, match="ENGINE_CLAUDE_BIN"):
        brain._claude_bin()
