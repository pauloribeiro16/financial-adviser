from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    import os
    import sys

    env = {k: v for k, v in os.environ.items() if k != "MINIMAX_API_KEY"}
    env["FA_SKIP_DOTENV"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "app.main", *args],
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
    )


def test_clean_mocks_removes_mock_dir(tmp_path: Path) -> None:
    """--clean-mocks deletes the entire out/mock/ directory."""
    fake_out = tmp_path / "out"
    fake_mock_root = fake_out / "mock"
    fake_mock = fake_mock_root / "company" / "AAPL"
    fake_mock.mkdir(parents=True)
    (fake_mock / "2026-07-01T00-00-00_001_mock_debate.md").write_text("mock")
    (fake_mock / "2026-07-01T00-00-00_001_mock_meta.json").write_text("{}")
    (fake_mock / "per_agent").mkdir()
    (fake_mock / "per_agent" / "buffett.md").write_text("p")

    result = _run_cli("--clean-mocks", cwd=tmp_path)
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"
    assert not fake_mock_root.exists(), (
        f"out/mock/ still exists; remaining: {list(fake_mock_root.rglob('*'))}"
    )
    assert "Removed 3 mock files" in result.stderr, (
        f"expected count message in stderr, got: {result.stderr!r}"
    )


def test_clean_mocks_handles_no_mock_dir(tmp_path: Path) -> None:
    """--clean-mocks when out/mock/ doesn't exist prints a clear message, no error."""
    result = _run_cli("--clean-mocks", cwd=tmp_path)
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "no mock" in result.stderr.lower(), (
        f"expected 'no mock' in stderr, got: {result.stderr!r}"
    )


def test_clean_mocks_preserves_out_real(tmp_path: Path) -> None:
    """--clean-mocks must NOT touch out/real/ (those are real analyses)."""
    fake_out = tmp_path / "out"
    real = fake_out / "real" / "company" / "SLB"
    real.mkdir(parents=True)
    real_file = real / "2026-07-05T15-23-19_130_minimax_debate.md"
    real_file.write_text("SLB analysis")

    mock = fake_out / "mock" / "company" / "AAPL"
    mock.mkdir(parents=True)
    (mock / "2026-07-01T00-00-00_001_mock_debate.md").write_text("mock")

    result = _run_cli("--clean-mocks", cwd=tmp_path)
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert not mock.exists(), "out/mock/company/AAPL should have been removed"
    assert real_file.exists(), "out/real/company/SLB/... must survive --clean-mocks"
