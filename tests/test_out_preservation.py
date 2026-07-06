from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_no_uncommitted_out_deletions() -> None:
    """out/ must not have uncommitted deletions in the working tree.

    Catches the failure mode where a subagent or implementation step
    deleted user analyses without committing the deletion (which would
    silently wipe their real analyses).
    """
    result = subprocess.run(
        ["git", "status", "--porcelain", "out/"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    deletions = [line for line in result.stdout.splitlines() if line.startswith(" D ") or line.startswith("D ")]
    assert not deletions, f"uncommitted deletions in out/: {deletions}"


def test_real_analyses_are_tracked() -> None:
    """Real-provider analyses in out/real/ must be git-tracked, not just on disk.

    Ensures real analyses survive a working-tree cleanup.
    """
    out_dir = REPO_ROOT / "out" / "real"
    if not out_dir.exists():
        return
    real_files = [p for p in out_dir.rglob("*_minimax_*") if p.is_file()]
    if not real_files:
        return
    result = subprocess.run(
        ["git", "ls-files", "out/real/"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    tracked = set(result.stdout.splitlines())
    untracked = [
        str(p.relative_to(REPO_ROOT))
        for p in real_files
        if str(p.relative_to(REPO_ROOT)) not in tracked
    ]
    assert not untracked, f"untracked real analyses: {untracked}"


def test_no_legacy_dirs() -> None:
    """No out/debate_* or out/run_* legacy dirs (those were S6-S10)."""
    out_dir = REPO_ROOT / "out"
    if not out_dir.exists():
        return
    legacy = [
        p for p in out_dir.iterdir()
        if p.is_dir() and (p.name.startswith("debate_") or p.name.startswith("run_"))
    ]
    assert not legacy, f"legacy dirs found: {legacy}"


def test_output_root_routes_by_provider() -> None:
    """output_root() must route mocks to out/mock/ and real to out/real/."""
    from app.formatter import output_root

    assert str(output_root("mock")).endswith("out/mock")
    assert str(output_root("minimax")).endswith("out/real")
    assert str(output_root("")).endswith("out/mock")
    assert str(output_root(None)).endswith("out/mock")
