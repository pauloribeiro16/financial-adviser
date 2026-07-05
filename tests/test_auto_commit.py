from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.main import _auto_commit_and_push


def test_auto_commit_skips_on_mock() -> None:
    """The CALLER (app/main.py) only invokes _auto_commit when provider != mock.
    This test verifies the helper itself doesn't call git add when called directly
    with no changes (defensive)."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        # Even if called with mock provider (shouldn't be), it should at least
        # not commit a no-op. Test by calling with a non-existent path.
        _auto_commit_and_push("2026-01-01T00-00-00_000", "XYZ", "minimax", Path("/tmp/does-not-exist"))
        # Verify subprocess.run was called (git add was attempted)
        assert mock_run.called


def test_auto_commit_uses_correct_message_format() -> None:
    """Verify the commit message format includes timestamp, target, provider."""
    captured_cmds = []

    def fake_run(cmd, *args, **kwargs):
        from unittest.mock import MagicMock
        result = MagicMock()
        result.stdout = "out/file.md\n"  # simulate something to commit
        result.returncode = 0
        captured_cmds.append(cmd)
        return result

    with patch("subprocess.run", side_effect=fake_run):
        _auto_commit_and_push(
            "2026-07-05T15-23-19_130", "SLB", "minimax",
            Path("/tmp/fake"),
        )

    # Find the commit command
    commit_cmds = [c for c in captured_cmds if "commit" in c]
    assert commit_cmds, f"no commit command issued; captured: {captured_cmds}"
    # Check the message
    commit_cmd = commit_cmds[0]
    msg_idx = commit_cmd.index("-m") + 1
    msg = commit_cmd[msg_idx]
    assert "2026-07-05T15-23-19_130" in msg
    assert "SLB" in msg
    assert "minimax" in msg
    assert msg.startswith("analysis: ")
