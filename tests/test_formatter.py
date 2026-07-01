from __future__ import annotations

from datetime import date
from io import StringIO

import pytest
from rich.console import Console

from app.formatter import render, render_debate_rich
from app.models import (
    Assessment,
    Consensus,
    DebateResult,
    Direction,
    Domain,
    Rebuttal,
    Thesis,
    Verdict,
)


def _make_debate_result(*, with_verdict: bool = True) -> DebateResult:
    theses = [
        Thesis(
            agent_id="buffett",
            target="AAPL",
            domain=Domain.COMPANY,
            round=0,
            verdict=Direction.BULLISH,
            conviction=0.72,
            key_drivers=["moat", "FCF", "balance sheet"],
            reasoning="Buffett reasoning first line.\nSecond paragraph.",
            data_used=["10-K"],
        ),
        Thesis(
            agent_id="taleb",
            target="AAPL",
            domain=Domain.COMPANY,
            round=0,
            verdict=Direction.BEARISH,
            conviction=0.45,
            key_drivers=["tail risk", "concentration"],
            reasoning="Taleb reasoning first line.\nSecond paragraph.",
            data_used=["options chain"],
        ),
    ]
    rebuttals = [
        Rebuttal(
            agent_id="buffett",
            target="AAPL",
            domain=Domain.COMPANY,
            round=1,
            targets=["taleb"],
            concessions=["tail risk is real"],
            disagreements=["moats still hold"],
            revised_verdict=Direction.BULLISH,
            revised_conviction=0.68,
            reasoning="Buffett rebuttal first line.",
        ),
        Rebuttal(
            agent_id="taleb",
            target="AAPL",
            domain=Domain.COMPANY,
            round=1,
            targets=["buffett"],
            concessions=["balance sheet is strong"],
            disagreements=["concentration remains"],
            revised_verdict=Direction.NEUTRAL,
            revised_conviction=0.5,
            reasoning="Taleb rebuttal first line.",
        ),
    ]
    verdict = None
    if with_verdict:
        verdict = Verdict(
            target="AAPL",
            domain=Domain.COMPANY,
            consensus=Consensus.SPLIT_BULL,
            bull_count=2,
            bear_count=0,
            neutral_count=1,
            avg_conviction=0.58,
            points_of_agreement=["both like the moat", "both worried about tail risk"],
            points_of_disagreement=["how to size the position"],
            final_call="Disagree on sizing, agree moats hold.",
            confidence=0.55,
            summary="Synthesized view across 2 rounds.",
        )
    return DebateResult(
        run_id="debate_test",
        domain=Domain.COMPANY,
        target="AAPL",
        target_date=date(2025, 3, 31),
        provider="mock",
        analysts=["buffett", "taleb"],
        theses=theses,
        rebuttals=rebuttals,
        verdict=verdict,
        created_at="2025-03-31T00:00:00",
    )


def _console_with_capture() -> tuple[Console, StringIO]:
    buf = StringIO()
    con = Console(file=buf, force_terminal=False, color_system=None, width=120)
    return con, buf


def test_render_debate_rich_with_verdict(capsys: pytest.CaptureFixture[str]) -> None:
    result = _make_debate_result(with_verdict=True)
    con, buf = _console_with_capture()
    render_debate_rich(result, console=con)
    captured = buf.getvalue()
    out = capsys.readouterr()
    assert "Debate" in captured
    assert "SYNTHESIS" in captured
    assert "buffett" in captured
    assert "taleb" in captured
    assert "BULLISH" in captured
    assert "BEARISH" in captured
    assert "NEUTRAL" in captured
    assert "Points of agreement" in captured
    assert "Points of disagreement" in captured
    assert out.err == "" or "Wrote" not in out.err


def test_render_debate_rich_without_verdict(capsys: pytest.CaptureFixture[str]) -> None:
    result = _make_debate_result(with_verdict=False)
    con, buf = _console_with_capture()
    render_debate_rich(result, console=con)
    captured = buf.getvalue()
    assert "Debate" in captured
    assert "SYNTHESIS" not in captured
    assert "buffett" in captured
    assert "taleb" in captured


def test_render_debate_rich_prints_non_empty(capsys: pytest.CaptureFixture[str]) -> None:
    result = _make_debate_result()
    con, buf = _console_with_capture()
    render_debate_rich(result, console=con)
    captured = buf.getvalue()
    assert len(captured) > 100, f"unexpectedly short output: {len(captured)} chars"


def test_render_md_legacy_sanity() -> None:
    a = Assessment(
        agent_id="buffett",
        indicator_id="US.FFR",
        target_date=date(2025, 3, 31),
        provider="mock",
        diagnosis="d",
        outlook="o",
        key_drivers=["k1"],
        news_interpretation="n",
        reasoning_trace="r",
        signal_direction="BULLISH",
        signal_strength=0.42,
    )
    md = render([a], meta={"target_date": "2025-03-31", "provider": "mock", "analysts": ["buffett"], "indicators": ["US.FFR"], "completed_at": "2025-03-31", "n_assessments": 1})
    assert "# Macro Assessment Run" in md
    assert "buffett" in md.lower()
    assert "BULLISH" in md
