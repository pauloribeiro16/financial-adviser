from __future__ import annotations

import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from app.agents import ALL_AGENTS
from app.catalog import ALL_CATALOG
from app.formatter import default_run_dir, render, render_per_agent, render_summary
from app.models import Assessment
from app.providers import MiniMaxProvider, ProviderRegistry
from app.runner import run

REPO_ROOT = Path("/Users/pauloribeiro/Desktop/Projetos/financial-adviser")
VALID_DIRECTIONS = {"BULLISH", "BEARISH", "NEUTRAL"}


def test_catalog_has_8_indicators() -> None:
    assert len(ALL_CATALOG) == 8
    ids = [i.indicator_id for i in ALL_CATALOG]
    assert len(ids) == len(set(ids)), f"duplicate IDs: {ids}"


def test_all_agents_registry_has_15_personas() -> None:
    assert len(ALL_AGENTS) == 15


def test_each_persona_has_unique_agent_id() -> None:
    expected_ids = {
        "buffett", "lynch", "dalio", "burry", "greenspan", "bernanke", "volcker",
        "dimon", "eisman", "grantham", "simons", "taleb", "wood", "gundlach", "thaler",
    }
    assert set(ALL_AGENTS.keys()) == expected_ids
    agent_ids = [cls.agent_id for cls in ALL_AGENTS.values()]
    assert len(agent_ids) == len(set(agent_ids)) == 15


def test_assessment_schema_round_trip() -> None:
    original = Assessment(
        agent_id="buffett",
        indicator_id="US.FFR",
        target_date=date(2025, 3, 31),
        provider="mock",
        diagnosis="Round-trip diagnosis.",
        outlook="Round-trip outlook.",
        key_drivers=["driver 1", "driver 2"],
        news_interpretation="Round-trip news.",
        reasoning_trace="Round-trip trace.",
        signal_direction="BULLISH",
        signal_strength=0.7,
    )
    data = original.model_dump()
    restored = Assessment(**data)
    assert restored == original


def test_mock_provider_returns_valid_assessment() -> None:
    agent_cls = ALL_AGENTS["buffett"]
    agent = agent_cls(provider_name="mock")
    assess = agent.generate_assessment("US.FFR", date(2025, 3, 31))
    assert isinstance(assess, Assessment)
    assert assess.agent_id == "buffett"
    assert assess.indicator_id == "US.FFR"
    assert 0.0 <= assess.signal_strength <= 1.0
    assert assess.signal_direction in VALID_DIRECTIONS


def test_runner_returns_correct_count() -> None:
    results = run(
        analysts=["buffett", "thaler"],
        indicators=["US.FFR", "US.UST10Y"],
        provider_name="mock",
    )
    assert len(results) == 4
    for r in results:
        assert isinstance(r, Assessment)
        assert 0.0 <= r.signal_strength <= 1.0
        assert r.signal_direction in VALID_DIRECTIONS


def test_formatter_md_contains_required_sections() -> None:
    a = Assessment(
        agent_id="buffett",
        indicator_id="US.FFR",
        target_date=date(2025, 3, 31),
        provider="mock",
        diagnosis="Test diagnosis.",
        outlook="Test outlook.",
        key_drivers=["alpha", "beta"],
        news_interpretation="Test news.",
        reasoning_trace="Test trace.",
        signal_direction="BULLISH",
        signal_strength=0.42,
    )
    md = render(
        [a],
        meta={
            "analysts": ["buffett"],
            "indicators": ["US.FFR"],
            "provider": "mock",
            "target_date": "2025-03-31",
            "completed_at": "2026-07-01",
            "n_assessments": 1,
        },
    )
    assert "# Macro Assessment Run" in md
    assert "## Summary" in md
    assert "| Analyst | Indicator | Signal | Strength |" in md
    assert "### Diagnosis" in md
    assert "### Outlook" in md
    assert "### Key drivers" in md
    assert "### News interpretation" in md
    assert "### Reasoning trace" in md
    assert "- alpha" in md and "- beta" in md


def test_cli_end_to_end_with_mock(tmp_path: Path) -> None:
    output = tmp_path / "out.md"
    result = subprocess.run(
        [
            sys.executable, "-m", "app.main",
            "--analysts", "buffett",
            "--indicators", "US.FFR",
            "--provider", "mock",
            "--output", str(output),
            "--env", "development",
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert output.exists()
    assert output.stat().st_size > 100
    content = output.read_text(encoding="utf-8")
    assert "# Macro Assessment Run" in content
    assert "buffett" in content.lower()


def test_minimax_provider_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without MINIMAX_API_KEY, MiniMaxProvider.get_model() raises ValueError."""
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    ProviderRegistry._providers.clear()
    ProviderRegistry.initialize_defaults()
    minimax = ProviderRegistry.get("minimax")
    assert isinstance(minimax, MiniMaxProvider)
    with pytest.raises(ValueError, match="MINIMAX_API_KEY"):
        minimax.get_model()


def test_runner_aborts_when_provider_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    """runner.run() raises a single RuntimeError instead of N failures when the
    provider is missing the API key."""
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    ProviderRegistry._providers.clear()
    ProviderRegistry.initialize_defaults()
    with pytest.raises(RuntimeError, match="MINIMAX_API_KEY"):
        run(["buffett", "burry", "dimon"], ["US.FFR", "US.UST10Y"], provider_name="minimax")


def test_cli_exits_2_when_api_key_missing(tmp_path: Path) -> None:
    """End-to-end: --provider minimax without MINIMAX_API_KEY exits with code 2 and
    a single clear error message on stderr."""
    output = tmp_path / "out.md"
    env = {k: v for k, v in __import__("os").environ.items() if k != "MINIMAX_API_KEY"}
    env["FA_SKIP_DOTENV"] = "1"  # bypass .env loading so the API key is truly absent
    result = subprocess.run(
        [
            sys.executable, "-m", "app.main",
            "--analysts", "buffett",
            "--indicators", "US.FFR",
            "--provider", "minimax",
            "--output", str(output),
            "--env", "development",
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 2, f"stderr: {result.stderr}"
    assert "MINIMAX_API_KEY" in result.stderr
    assert "mock" in result.stderr  # the hint
    assert not output.exists()  # no MD written when run fails


def test_per_agent_layout(tmp_path: Path) -> None:
    """render_per_agent + render_summary produce correct tree structure."""
    a1 = Assessment(
        agent_id="buffett", indicator_id="US.FFR", target_date=date(2025, 3, 31),
        provider="minimax", diagnosis="d1", outlook="o1", key_drivers=["x", "y"],
        news_interpretation="n1", reasoning_trace="r1",
        signal_direction="BULLISH", signal_strength=0.42,
    )
    a2 = Assessment(
        agent_id="buffett", indicator_id="US.UST10Y", target_date=date(2025, 3, 31),
        provider="minimax", diagnosis="d2", outlook="o2", key_drivers=["z"],
        news_interpretation="", reasoning_trace="",
        signal_direction="BEARISH", signal_strength=0.7,
    )
    a3 = Assessment(
        agent_id="taleb", indicator_id="US.FFR", target_date=date(2025, 3, 31),
        provider="minimax", diagnosis="d3", outlook="o3", key_drivers=["a"],
        news_interpretation="n3", reasoning_trace="r3",
        signal_direction="NEUTRAL", signal_strength=0.55,
    )
    meta = {
        "run_id": "run_test",
        "target_date": "2025-03-31",
        "provider": "minimax",
        "analysts": ["buffett", "taleb"],
        "indicators": ["US.FFR", "US.UST10Y"],
        "completed_at": "2026-07-01",
    }
    tree = render_per_agent([a1, a2, a3], meta)
    assert set(tree.keys()) == {"buffett", "taleb"}
    assert len(tree["buffett"]) == 2
    assert len(tree["taleb"]) == 1
    indicator_id, md = tree["buffett"][0]
    assert indicator_id in {"US.FFR", "US.UST10Y"}
    assert "# Warren E. Buffett on" in md
    assert "### Diagnosis" in md
    assert "### Outlook" in md
    assert "### Key drivers" in md
    assert "### News interpretation" in md
    assert "### Reasoning trace" in md
    assert "BULLISH" in md or "BEARISH" in md
    summary = render_summary([a1, a2, a3], meta)
    assert "# Run summary" in summary
    assert "| Persona |" in summary
    assert "buffett/US.FFR.md" in summary
    assert default_run_dir().startswith("./out/run_")


def test_default_single_indicator(tmp_path: Path) -> None:
    """Without --indicators, only US.UST10Y is assessed (default single)."""
    env = {k: v for k, v in __import__("os").environ.items() if k != "MINIMAX_API_KEY"}
    env["FA_SKIP_DOTENV"] = "1"
    output_dir = tmp_path / "out"
    result = subprocess.run(
        [
            sys.executable, "-m", "app.main",
            "--analysts", "buffett",
            "--provider", "mock",
            "--output", str(output_dir),
            "--env", "development",
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    files = sorted(output_dir.rglob("*.md"))
    paths = {p.relative_to(output_dir).as_posix() for p in files}
    assert any(p.endswith("_assessment.md") for p in paths), paths
    assert any(p.endswith("_summary.md") for p in paths), paths
    assert any("per_agent/buffett_US.UST10Y" in p for p in paths), paths
