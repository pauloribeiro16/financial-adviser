from __future__ import annotations

from datetime import date

import pytest

from app.debate.orchestrator import orchestrate_debate
from app.models import DebateResult, Domain, Rebuttal, Verdict
from app.providers import ProviderRegistry
from tests._mock_provider import SchemaAwareMockProvider


@pytest.fixture
def schema_aware_mock():
    ProviderRegistry.register("mock", SchemaAwareMockProvider())
    yield
    ProviderRegistry._providers.pop("mock", None)


def test_orchestrator_with_schema_aware_mock(schema_aware_mock) -> None:
    result = orchestrate_debate(
        analysts=["buffett", "taleb"],
        target="AAPL",
        domain="company",
        target_date=date(2025, 3, 31),
        rounds=2,
        provider_name="mock",
        include_synthesis=True,
        ctx={
            "ticker": "AAPL",
            "edgar": {"submissions": {"name": "Apple Inc.", "sic": "3571"}, "latest_10k": None, "facts": {}},
            "quote": {"price": 200.0, "previous_close": 198.0},
            "fundamentals": {},
        },
    )
    assert isinstance(result, DebateResult)
    assert result.target == "AAPL"
    assert result.domain == Domain.COMPANY
    assert {t.agent_id for t in result.theses} == {"buffett", "taleb"}
    assert all(t.round == 0 for t in result.theses)
    assert len(result.rebuttals) >= 2
    assert result.verdict is not None
    assert isinstance(result.verdict, Verdict)
    assert any(isinstance(rb, Rebuttal) for rb in result.rebuttals)


def test_orchestrator_without_langfuse_keys(
    monkeypatch: pytest.MonkeyPatch, schema_aware_mock
) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)

    result = orchestrate_debate(
        analysts=["buffett", "taleb"],
        target="AAPL",
        domain="company",
        target_date=date(2025, 3, 31),
        rounds=2,
        provider_name="mock",
        include_synthesis=True,
        ctx={
            "ticker": "AAPL",
            "edgar": {"submissions": {}, "latest_10k": None, "facts": {}},
            "quote": {},
            "fundamentals": {},
        },
    )
    assert isinstance(result, DebateResult)
    assert result.verdict is not None
    assert len(result.theses) >= 1


def test_orchestrator_single_round_no_rebuttals(schema_aware_mock) -> None:
    result = orchestrate_debate(
        analysts=["buffett"],
        target="AAPL",
        domain="company",
        target_date=date(2025, 3, 31),
        rounds=1,
        provider_name="mock",
        include_synthesis=True,
        ctx={
            "ticker": "AAPL",
            "edgar": {"submissions": {}, "latest_10k": None, "facts": {}},
            "quote": {},
            "fundamentals": {},
        },
    )
    assert isinstance(result, DebateResult)
    assert len(result.theses) == 1
    assert result.rebuttals == []
    assert result.verdict is not None
