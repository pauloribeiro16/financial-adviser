from __future__ import annotations

from datetime import date

from app.models import (
    Assessment,
    Consensus,
    DebateResult,
    Direction,
    Domain,
    Rebuttal,
    Thesis,
    Verdict,
    _coerce_str_list,
)


def test_coerce_handles_nested_lists_with_xml_tags() -> None:
    raw = [["<item>I concede to Wood that the valuation is stretched.</item>"],
            ["I push back against Bernanke: rates aren't the only signal."]]
    rb = Rebuttal(
        agent_id="dalio",
        target="TSLA",
        domain=Domain.COMPANY,
        round=1,
        targets=[["wood"], ["bernanke"]],
        concessions=raw[0],
        disagreements=raw[1],
        revised_verdict=Direction.NEUTRAL,
        revised_conviction=0.5,
        reasoning="r",
    )
    assert rb.concessions == ["I concede to Wood that the valuation is stretched."]
    assert rb.disagreements == ["I push back against Bernanke: rates aren't the only signal."]
    assert rb.targets == ["wood", "bernanke"]


def test_coerce_handles_flat_list_of_xml_tagged_strings() -> None:
    rb = Rebuttal(
        agent_id="x",
        target="AAPL",
        domain=Domain.COMPANY,
        round=1,
        targets=["wood", "bernanke"],
        concessions=["<item>one</item>", "<item>two</item>"],
        disagreements=["<item>three</item>"],
        revised_verdict=Direction.NEUTRAL,
        revised_conviction=0.5,
        reasoning="r",
    )
    assert rb.concessions == ["one", "two"]
    assert rb.disagreements == ["three"]


def test_coerce_handles_none_and_empty() -> None:
    assert _coerce_str_list(None) == []
    assert _coerce_str_list("") == []
    assert _coerce_str_list([]) == []
    assert _coerce_str_list(["", "  ", "real"]) == ["real"]


def test_thesis_key_drivers_coerced() -> None:
    t = Thesis(
        agent_id="x",
        target="AAPL",
        domain=Domain.COMPANY,
        round=0,
        verdict=Direction.BULLISH,
        conviction=0.6,
        key_drivers=[["<item>driver 1</item>"], "<item>driver 2</item>"],
        reasoning="r",
        data_used=[["P/E"], "ROE"],
    )
    assert t.key_drivers == ["driver 1", "driver 2"]
    assert t.data_used == ["P/E", "ROE"]


def test_verdict_points_lists_coerced() -> None:
    v = Verdict(
        target="AAPL",
        domain=Domain.COMPANY,
        consensus=Consensus.NEUTRAL,
        bull_count=1,
        bear_count=1,
        neutral_count=1,
        avg_conviction=0.5,
        points_of_agreement=[["<item>ag 1</item>"]],
        points_of_disagreement=[["<item>dis 1</item>"], "dis 2"],
        final_call="x",
        confidence=0.5,
        summary="s",
    )
    assert v.points_of_agreement == ["ag 1"]
    assert v.points_of_disagreement == ["dis 1", "dis 2"]


def test_assessment_key_drivers_coerced() -> None:
    a = Assessment(
        agent_id="x",
        indicator_id="US.FFR",
        target_date=date.today(),
        provider="mock",
        diagnosis="d",
        outlook="o",
        key_drivers=[["<item>k1</item>"], "k2"],
        news_interpretation="",
        reasoning_trace="",
        signal_direction="NEUTRAL",
        signal_strength=0.5,
    )
    assert a.key_drivers == ["k1", "k2"]


def test_rebuttal_constructible_from_real_minimax_failure_payload() -> None:
    raw_minimax = {
        "concessions": [["<item>I concede to Wood that...</item>"],
                         "<item>I concede to Burry...</item>"],
        "disagreements": [["<item>I push back against Bernanke...</item>"],
                          "<item>I disagree with Eisman...</item>"],
        "targets": [["wood"], "burry", "<item>bernanke</item>"],
        "revised_verdict": "BEARISH",
        "revised_conviction": 0.55,
        "reasoning": "raw reasoning",
    }
    rb = Rebuttal(agent_id="taleb", target="TSLA", domain=Domain.COMPANY, round=1, **raw_minimax)
    assert rb.concessions == ["I concede to Wood that...", "I concede to Burry..."]
    assert rb.disagreements == ["I push back against Bernanke...", "I disagree with Eisman..."]
    assert rb.targets == ["wood", "burry", "bernanke"]


def test_debate_result_analysts_coerced() -> None:
    dr = DebateResult(
        run_id="r",
        domain=Domain.COMPANY,
        target="AAPL",
        target_date=date.today(),
        provider="mock",
        analysts=[["<item>buffett</item>"], "taleb"],
        theses=[],
        rebuttals=[],
        created_at="2026-07-02T00:00:00",
    )
    assert dr.analysts == ["buffett", "taleb"]
