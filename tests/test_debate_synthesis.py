from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest

from app.debate.engine import build_verdict_messages, run_debate
from app.models import (
    Consensus,
    DebateResult,
    Direction,
    Domain,
    Rebuttal,
    Thesis,
    Verdict,
)
from app.providers import LLMProvider, ProviderRegistry


def _make_thesis(
    agent_id: str, verdict: Direction, conviction: float, target: str = "AAPL"
) -> Thesis:
    return Thesis(
        agent_id=agent_id,
        target=target,
        domain=Domain.COMPANY,
        round=0,
        verdict=verdict,
        conviction=conviction,
        key_drivers=["driver"],
        reasoning=f"reasoning for {agent_id}",
        data_used=["data"],
    )


def _make_rebuttal(
    agent_id: str,
    revised: Direction,
    conviction: float,
    round_idx: int = 1,
    target: str = "AAPL",
) -> Rebuttal:
    return Rebuttal(
        agent_id=agent_id,
        target=target,
        domain=Domain.COMPANY,
        round=round_idx,
        targets=["other"],
        concessions=["c"],
        disagreements=["d"],
        revised_verdict=revised,
        revised_conviction=conviction,
        reasoning=f"rebuttal from {agent_id}",
    )


def _json_response(payload: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(content=json.dumps(payload))


class _FailingStructuredVerdictModel:
    """Structured Verdict calls raise; plain invoke returns JSON.

    Thesis and Rebuttal structured calls succeed so the debate runs end to end.
    """

    def __init__(self, schema: Any = None) -> None:
        self._schema = schema

    def with_structured_output(self, schema: Any) -> _FailingStructuredVerdictModel:
        return _FailingStructuredVerdictModel(schema)

    def bind_tools(self, tools: Any) -> _FailingStructuredVerdictModel:
        return self

    def invoke(self, messages: Any, config: Any = None) -> Any:
        s = self._schema
        if s is Verdict:
            raise RuntimeError("simulated structured output failure for Verdict")
        if s is Thesis:
            return Thesis(
                agent_id="mock",
                target="AAPL",
                domain=Domain.COMPANY,
                round=0,
                verdict=Direction.BULLISH,
                conviction=0.6,
                key_drivers=["d1"],
                reasoning="mock thesis",
                data_used=["P/E"],
            )
        if s is Rebuttal:
            return Rebuttal(
                agent_id="mock",
                target="AAPL",
                domain=Domain.COMPANY,
                round=1,
                targets=["other"],
                concessions=["c1"],
                disagreements=["d1"],
                revised_verdict=Direction.NEUTRAL,
                revised_conviction=0.55,
                reasoning="mock rebuttal",
            )
        return _json_response(
            {
                "final_call": "BULLISH on balance",
                "summary": "The debate leans positive on AAPL after the rebuttals.",
                "confidence": 0.72,
                "points_of_agreement": ["Both see strong FCF", "Margin concerns shared"],
                "points_of_disagreement": ["Magnitude of growth differs"],
            }
        )


class _FailingStructuredVerdictProvider(LLMProvider):
    def provider_name(self) -> str:
        return "mock"

    def get_model(self) -> _FailingStructuredVerdictModel:
        return _FailingStructuredVerdictModel()


class _CapturingVerdictModel:
    """Captures messages sent to structured Verdict call; returns a default Verdict.

    A single shared ``captured`` list is used across all instances produced by
    ``with_structured_output`` so the test can read it from the provider.
    """

    captured: list[Any] = []

    def __init__(self, schema: Any = None) -> None:
        self._schema = schema

    def with_structured_output(self, schema: Any) -> _CapturingVerdictModel:
        return _CapturingVerdictModel(schema)

    def bind_tools(self, tools: Any) -> _CapturingVerdictModel:
        return self

    def invoke(self, messages: Any, config: Any = None) -> Any:
        s = self._schema
        if s is Verdict:
            _CapturingVerdictModel.captured.append(messages)
            return Verdict(
                target="AAPL",
                domain=Domain.COMPANY,
                consensus=Consensus.SPLIT_BULL,
                bull_count=2,
                bear_count=0,
                neutral_count=0,
                avg_conviction=0.6,
                points_of_agreement=["a"],
                points_of_disagreement=["d"],
                final_call="Split bull",
                confidence=0.6,
                summary="captured",
            )
        if s is Thesis:
            return Thesis(
                agent_id="mock",
                target="AAPL",
                domain=Domain.COMPANY,
                round=0,
                verdict=Direction.BULLISH,
                conviction=0.6,
                key_drivers=["d1"],
                reasoning="mock thesis",
                data_used=["P/E"],
            )
        if s is Rebuttal:
            return Rebuttal(
                agent_id="mock",
                target="AAPL",
                domain=Domain.COMPANY,
                round=1,
                targets=["other"],
                concessions=["c1"],
                disagreements=["d1"],
                revised_verdict=Direction.NEUTRAL,
                revised_conviction=0.55,
                reasoning="mock rebuttal",
            )
        return SimpleNamespace(content="{}")


class _CapturingVerdictProvider(LLMProvider):
    def __init__(self) -> None:
        self._model = _CapturingVerdictModel()

    def provider_name(self) -> str:
        return "mock"

    def get_model(self) -> _CapturingVerdictModel:
        return self._model


@pytest.fixture
def failing_structured_provider() -> Any:
    ProviderRegistry.register("mock", _FailingStructuredVerdictProvider())
    yield
    ProviderRegistry._providers.pop("mock", None)


@pytest.fixture
def capturing_provider() -> Any:
    _CapturingVerdictModel.captured = []
    prov = _CapturingVerdictProvider()
    ProviderRegistry.register("mock", prov)
    yield prov
    ProviderRegistry._providers.pop("mock", None)


def test_json_fallback_produces_non_heuristic_verdict(failing_structured_provider) -> None:
    result = run_debate(
        analysts=["buffett", "taleb"],
        target="AAPL",
        domain="company",
        target_date=date(2025, 3, 31),
        context_md="FY24 P/E 22, FCF $80B, net cash $30B.",
        rounds=1,
        provider_name="mock",
    )
    assert isinstance(result, DebateResult)
    assert result.verdict is not None
    assert isinstance(result.verdict, Verdict)
    assert not result.verdict.summary.startswith("Heuristic fallback")
    assert "The debate leans positive on AAPL" in result.verdict.summary
    assert result.verdict.points_of_agreement
    assert "Both see strong FCF" in result.verdict.points_of_agreement
    assert result.verdict.final_call == "BULLISH on balance"
    assert result.verdict.confidence == pytest.approx(0.72)


def test_prompt_contains_precomputed_tally(capturing_provider) -> None:
    theses = [
        _make_thesis("buffett", Direction.BULLISH, 0.7),
        _make_thesis("lynch", Direction.BULLISH, 0.65),
        _make_thesis("taleb", Direction.BEARISH, 0.8),
    ]
    rebuttals = [
        _make_rebuttal("buffett", Direction.BULLISH, 0.75, round_idx=1),
        _make_rebuttal("lynch", Direction.NEUTRAL, 0.5, round_idx=1),
        _make_rebuttal("taleb", Direction.BEARISH, 0.85, round_idx=1),
    ]
    build_verdict_messages(
        target="AAPL",
        domain="company",
        target_date=date(2025, 3, 31),
        context_md="ctx",
        theses=theses,
        rebuttals=rebuttals,
    )
    run_debate(
        analysts=["buffett", "taleb"],
        target="AAPL",
        domain="company",
        target_date=date(2025, 3, 31),
        context_md="FY24 P/E 22.",
        rounds=1,
        provider_name="mock",
    )
    captured = _CapturingVerdictModel.captured
    assert captured, "expected at least one captured Verdict invocation"
    user_msg = captured[-1][-1]["content"]
    assert "Position tally" in user_msg
    assert "bull:" in user_msg
    assert "bear:" in user_msg
    assert "neutral:" in user_msg
    assert "suggested_consensus:" in user_msg
    assert "ground truth" in user_msg.lower()


def test_precomputed_counts_overwrite_structured_output(capturing_provider) -> None:
    result = run_debate(
        analysts=["buffett", "taleb"],
        target="AAPL",
        domain="company",
        target_date=date(2025, 3, 31),
        context_md="ctx",
        rounds=1,
        provider_name="mock",
    )
    assert result.verdict is not None
    assert result.verdict.bull_count == 2
    assert result.verdict.bear_count == 0
    assert result.verdict.neutral_count == 0
    assert result.verdict.consensus == Consensus.BULLISH
    assert result.verdict.avg_conviction == pytest.approx(0.6)


def test_include_synthesis_false_skips_synthesis(capturing_provider) -> None:
    result = run_debate(
        analysts=["buffett", "taleb"],
        target="AAPL",
        domain="company",
        target_date=date(2025, 3, 31),
        context_md="ctx",
        rounds=1,
        provider_name="mock",
        include_synthesis=False,
    )
    assert isinstance(result, DebateResult)
    assert result.verdict is None
    assert _CapturingVerdictModel.captured == []
