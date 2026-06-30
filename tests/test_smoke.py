from __future__ import annotations

import subprocess
import sys
from datetime import date
from pathlib import Path

from app.agents import ALL_AGENTS
from app.catalog import ALL_CATALOG
from app.formatter import render
from app.models import Assessment
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
            "--format", "md",
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
