from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path("/Users/pauloribeiro/Desktop/Projetos/financial-adviser")


def _run_cli(*args: str, env_override: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k != "MINIMAX_API_KEY"}
    env["FA_SKIP_DOTENV"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    if env_override:
        env.update(env_override)
    return subprocess.run(
        [sys.executable, "-m", "app.main", *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=env,
    )


def test_cli_company_debate_with_mock(tmp_path: Path) -> None:
    output = tmp_path / "debate.md"
    result = _run_cli(
        "--company", "AAPL",
        "--analysts", "buffett,taleb",
        "--provider", "mock",
        "--rounds", "1",
        "--format", "debate",
        "--output", str(output),
        "--env", "development",
    )
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"
    assert output.exists(), f"output not written; stderr: {result.stderr}"
    text = output.read_text(encoding="utf-8")
    assert "Round 0" in text
    assert "taleb" in text
    assert "SYNTHESIS" in text or "Synthesis" in text


def test_cli_company_indicators_mutually_exclusive() -> None:
    result = _run_cli(
        "--company", "AAPL",
        "--indicators", "US.FFR",
        "--provider", "mock",
        "--env", "development",
    )
    assert result.returncode == 2
    err = result.stderr.lower()
    assert "exclusive" in err or "mutually" in err, f"stderr: {result.stderr}"


def test_cli_macro_default_single_indicator(tmp_path: Path) -> None:
    output = tmp_path / "out.md"
    result = _run_cli(
        "--analysts", "buffett",
        "--provider", "mock",
        "--format", "md",
        "--output", str(output),
        "--env", "development",
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert output.exists(), f"output not written; stderr: {result.stderr}"
    text = output.read_text(encoding="utf-8")
    assert text.startswith("# Macro Assessment Run")
