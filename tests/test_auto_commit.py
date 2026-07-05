from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.main import _auto_commit_and_push


def test_auto_commit_uses_correct_message_format() -> None:
    """Verify the commit message format: 'analysis: <TS> <TARGET> <PROVIDER>'."""
    captured: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):
        result = MagicMock()
        result.stdout = (
            "out/real/company/energy/SLB/"
            "2026-07-05T15-23-19_130_minimax_debate.md\n"
        )
        result.returncode = 0
        captured.append(cmd)
        return result

    with patch("subprocess.run", side_effect=fake_run):
        _auto_commit_and_push(
            "2026-07-05T15-23-19_130", "SLB", "minimax",
            Path("out/real/company/energy/SLB/2026-07-05T15-23-19_130_minimax"),
        )

    commit_cmds = [c for c in captured if "commit" in c]
    assert commit_cmds, f"no commit issued; captured: {captured}"
    msg = commit_cmds[0][commit_cmds[0].index("-m") + 1]
    assert msg.startswith("analysis: "), msg
    assert "2026-07-05T15-23-19_130" in msg
    assert "SLB" in msg
    assert "minimax" in msg


def test_auto_commit_skips_when_nothing_to_commit() -> None:
    """If `git diff --cached` is empty, skip both commit and push."""
    def fake_run(cmd, *args, **kwargs):
        result = MagicMock()
        result.stdout = ""
        result.returncode = 0
        return result

    with patch("subprocess.run", side_effect=fake_run) as mr:
        _auto_commit_and_push(
            "ts", "T", "minimax",
            Path("out/real/company/x/T/2026-01-01T00-00-00_000_minimax"),
        )

    cmds = [call.args[0] for call in mr.call_args_list]
    assert not any("commit" in c for c in cmds), f"commit was called; cmds: {cmds}"
    assert not any(
        isinstance(c, list) and len(c) >= 2 and c[:2] == ["git", "push"]
        for c in cmds
    ), f"push was called; cmds: {cmds}"


def test_auto_commit_swallows_errors() -> None:
    """A git failure must NOT raise — only log a warning."""
    def fake_run(cmd, *args, **kwargs):
        raise subprocess.CalledProcessError(
            returncode=128, cmd=cmd,
            output=b"", stderr=b"fatal: not a git repository",
        )

    with patch("subprocess.run", side_effect=fake_run):
        _auto_commit_and_push("ts", "T", "minimax", Path("/tmp/x"))


def test_auto_commit_swallows_timeout() -> None:
    """A git timeout must NOT raise — only log a warning."""
    def fake_run(cmd, *args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=5)

    with patch("subprocess.run", side_effect=fake_run):
        _auto_commit_and_push("ts", "T", "minimax", Path("/tmp/x"))


def test_auto_commit_swallows_missing_git() -> None:
    """If git is not on PATH, the helper must NOT raise."""
    def fake_run(cmd, *args, **kwargs):
        raise FileNotFoundError("git not found")

    with patch("subprocess.run", side_effect=fake_run):
        _auto_commit_and_push("ts", "T", "minimax", Path("/tmp/x"))
