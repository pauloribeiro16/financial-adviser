from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DEBATE_NAME = "2026-07-03T12-00-00_000_mock_debate.md"
SAMPLE_META_NAME = "2026-07-03T12-00-00_000_mock_meta.json"
SAMPLE_DEBATE = (
    "# Debate — XOM (Energy)\n"
    "## Round 0\n\n"
    "### buffett\n- Verdict: BULLISH\n"
    "- Reasoning: solid moat, FCF compounding at 8%, low capex.\n"
)
SAMPLE_META = (
    '{"ticker": "XOM", "sector": "Energy", "rounds": 1, '
    '"provider": "mock", "analysts": ["buffett"], "avg_conviction": 0.65}'
)


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
        cwd=os.getcwd(),
        env=env,
    )


def _seed_sample_debate(tmp_path: Path, ticker: str = "XOM", sector: str = "Energy") -> Path:
    ticker_dir = tmp_path / "out" / "company" / sector / ticker
    ticker_dir.mkdir(parents=True, exist_ok=True)
    (ticker_dir / SAMPLE_DEBATE_NAME).write_text(SAMPLE_DEBATE, encoding="utf-8")
    (ticker_dir / SAMPLE_META_NAME).write_text(SAMPLE_META, encoding="utf-8")
    return ticker_dir


@pytest.fixture()
def watch_seed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    _seed_sample_debate(tmp_path)
    return tmp_path


def test_help_shows_watch_subcommand() -> None:
    result = _run_cli("--help")
    assert result.returncode == 0
    text = (result.stdout or "") + (result.stderr or "")
    assert "watch" in text
    assert "{watch}" in text or "watch" in text


def test_watch_subcommand_help_describes_flags() -> None:
    result = _run_cli("watch", "--help")
    assert result.returncode == 0
    out = (result.stdout or "") + (result.stderr or "")
    assert "--sector" in out
    assert "--ticker" in out
    assert "--all" in out
    assert "--provider" in out
    assert "--output" in out


def test_watch_subcommand_alone_exits_0_with_help() -> None:
    result = _run_cli("watch")
    assert result.returncode == 0
    out = (result.stdout or "") + (result.stderr or "")
    assert "--sector" in out or "Available sectors" in out


def test_watch_unknown_sector_exits_1(watch_seed: Path) -> None:
    result = _run_cli("watch", "--sector", "NonExistent", "--provider", "mock")
    assert result.returncode == 1
    err = (result.stderr or "").lower()
    assert "unknown" in err or "available" in err
    assert "nonexistent" in err


def test_watch_sector_and_all_are_mutually_exclusive(watch_seed: Path) -> None:
    result = _run_cli(
        "watch", "--sector", "Energy", "--all",
        "--provider", "mock",
    )
    assert result.returncode == 2
    err = (result.stderr or "").lower()
    assert "mutually" in err or "exclusive" in err


def test_watch_energy_with_mock_writes_current_md(watch_seed: Path) -> None:
    output_root = watch_seed / "out" / "surveillance"
    result = _run_cli(
        "watch", "--sector", "Energy",
        "--provider", "mock",
        "--output", str(output_root),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"
    err = result.stderr or ""
    assert "watch" in err.lower() or "Done:" in err
    assert "written" in err.lower()

    current = output_root / "energy" / "XOM" / "current.md"
    assert current.exists(), f"current.md missing at {current}"
    text = current.read_text(encoding="utf-8")
    assert "## Summary (5 bullets)" in text
    assert "**Moat:**" in text
    assert "**Cycle:**" in text
    assert "**Financial Health:**" in text
    assert "**Valuation:**" in text
    assert "**Risks:**" in text
    assert "## Sector indicators" in text
    assert "## Buy target" in text
    assert "**Buy at:**" in text
    assert "## Trail of debates" in text

    index = output_root / "energy" / "_index.md"
    assert index.exists(), f"_index.md missing at {index}"
    idx_text = index.read_text(encoding="utf-8")
    assert "| Ticker | Name | Verdict | Buy @ | Conviction | Last |" in idx_text
    assert "XOM" in idx_text

    history = output_root / "energy" / "XOM" / "history.json"
    assert history.exists()


def test_watch_single_ticker_with_mock(watch_seed: Path) -> None:
    output_root = watch_seed / "out" / "surveillance"
    result = _run_cli(
        "watch", "--sector", "Energy", "--ticker", "XOM",
        "--provider", "mock",
        "--output", str(output_root),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"
    current = output_root / "energy" / "XOM" / "current.md"
    assert current.exists()
    other = output_root / "energy" / "CVX" / "current.md"
    assert not other.exists()


def test_watch_all_sectors_without_debates_returns_zero(watch_seed: Path) -> None:
    output_root = watch_seed / "out" / "surveillance"
    result = _run_cli(
        "watch", "--all",
        "--provider", "mock",
        "--output", str(output_root),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"
    assert (output_root / "energy" / "_index.md").exists()


def test_existing_debate_cli_still_works(tmp_path: Path) -> None:
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
    assert output.exists()


def test_watch_imports_resolve() -> None:
    from app.main import _parse_args
    from app.watch.cli import cmd_watch
    from app.watch.sector_runner import run_sector

    ns = _parse_args(["watch", "--sector", "Energy"])
    assert ns.subcommand == "watch"
    assert ns.sector == "Energy"

    assert callable(cmd_watch)
    assert callable(run_sector)
