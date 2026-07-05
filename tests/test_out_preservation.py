from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_no_uncommitted_out_deletions() -> None:
    """out/ must not have uncommitted deletions in the working tree.

    This catches the failure mode where a subagent or implementation step
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
    """Any real-provider analysis in out/ must be git-tracked, not just on disk.

    This ensures real analyses survive a working-tree cleanup.
    """
    out_dir = REPO_ROOT / "out"
    if not out_dir.exists():
        return  # nothing to check
    real_files = [
        p for p in out_dir.rglob("*_minimax_*")
        if p.is_file()
    ]
    if not real_files:
        return  # no real analyses yet
    result = subprocess.run(
        ["git", "ls-files", "out/"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    tracked = set(result.stdout.splitlines())
    untracked_real = [
        str(p.relative_to(REPO_ROOT))
        for p in real_files
        if str(p.relative_to(REPO_ROOT)) not in tracked
    ]
    assert not untracked_real, f"untracked real analyses: {untracked_real}"


def test_no_legacy_dirs_existed_at_s18_start() -> None:
    """sentinel: at S18 start, no out/debate_* or out/run_* dirs (those were the S6-S10 legacy format)."""
    out_dir = REPO_ROOT / "out"
    if not out_dir.exists():
        return
    legacy = [p for p in out_dir.iterdir() if p.is_dir() and (p.name.startswith("debate_") or p.name.startswith("run_"))]
    assert not legacy, f"legacy dirs found (should have been cleaned): {legacy}"
