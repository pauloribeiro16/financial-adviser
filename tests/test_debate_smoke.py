from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.debate.engine import run_debate
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


class _SchemaAwareMockModel:
    """Mock model that returns a valid Pydantic instance of whichever schema
    was passed to ``with_structured_output(...)``.

    Replaces ``MockModel`` for the duration of debate-engine tests via
    ``ProviderRegistry.register`` — keeps providers.py untouched.
    """

    def __init__(self, schema=None) -> None:
        self._schema = schema

    def with_structured_output(self, schema):
        return _SchemaAwareMockModel(schema)

    def bind_tools(self, tools):
        return self

    def invoke(self, messages, config=None):
        s = self._schema
        if s is Thesis:
            return Thesis(
                agent_id="mock",
                target="AAPL",
                domain=Domain.COMPANY,
                round=0,
                verdict=Direction.BULLISH,
                conviction=0.6,
                key_drivers=["mock driver a", "mock driver b"],
                reasoning="[MOCK thesis] placeholder reasoning.",
                data_used=["P/E ratio"],
            )
        if s is Rebuttal:
            return Rebuttal(
                agent_id="mock",
                target="AAPL",
                domain=Domain.COMPANY,
                round=1,
                targets=["other"],
                concessions=["concession 1"],
                disagreements=["disagreement 1"],
                revised_verdict=Direction.NEUTRAL,
                revised_conviction=0.55,
                reasoning="[MOCK rebuttal] placeholder reasoning.",
            )
        if s is Verdict:
            return Verdict(
                target="AAPL",
                domain=Domain.COMPANY,
                consensus=Consensus.SPLIT_BULL,
                bull_count=2,
                bear_count=0,
                neutral_count=0,
                avg_conviction=0.58,
                points_of_agreement=["Both see value"],
                points_of_disagreement=[],
                final_call="[MOCK] Split bull consensus",
                confidence=0.58,
                summary="[MOCK] Summary of debate.",
            )
        msg = f"unexpected schema: {s}"
        raise AssertionError(msg)


class _SchemaAwareMockProvider(LLMProvider):
    def provider_name(self) -> str:
        return "mock"

    def get_model(self):
        return _SchemaAwareMockModel()


@pytest.fixture
def schema_aware_mock():
    ProviderRegistry.register("mock", _SchemaAwareMockProvider())
    yield
    ProviderRegistry._providers.pop("mock", None)


def test_debate_runs_end_to_end_with_mock(schema_aware_mock) -> None:
    result = run_debate(
        analysts=["buffett", "taleb"],
        target="AAPL",
        domain="company",
        target_date=date(2025, 3, 31),
        context_md="FY24 P/E 22, FCF $80B, net cash $30B.",
        rounds=2,
        provider_name="mock",
    )
    assert isinstance(result, DebateResult)
    assert result.target == "AAPL"
    assert result.domain == Domain.COMPANY
    assert {t.agent_id for t in result.theses} == {"buffett", "taleb"}
    assert all(t.round == 0 for t in result.theses)
    assert len(result.rebuttals) >= 2
    assert result.verdict is not None
    assert isinstance(result.verdict, Verdict)
    assert isinstance(result.verdict.consensus, Consensus)


def test_debate_thesis_validation() -> None:
    base = {
        "agent_id": "buffett",
        "target": "AAPL",
        "domain": Domain.COMPANY,
        "round": 0,
        "verdict": Direction.BULLISH,
        "key_drivers": ["a", "b"],
        "reasoning": "r",
        "data_used": ["d"],
    }
    Thesis(**base, conviction=0.5)
    Thesis(**base, conviction=0.0)
    Thesis(**base, conviction=1.0)
    with pytest.raises(ValidationError):
        Thesis(**base, conviction=1.5)
    with pytest.raises(ValidationError):
        Thesis(**base, conviction=-0.1)


def test_debate_runs_single_round(schema_aware_mock) -> None:
    result = run_debate(
        analysts=["buffett", "taleb"],
        target="AAPL",
        domain="company",
        target_date=date(2025, 3, 31),
        context_md="Some context.",
        rounds=1,
        provider_name="mock",
    )
    assert isinstance(result, DebateResult)
    assert len(result.theses) == 2
    assert result.rebuttals == []
    assert result.verdict is not None
