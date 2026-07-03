from __future__ import annotations

from pathlib import Path

import pytest

from app.watch.aggregator import WatchSummary, aggregate_one
from app.watch.reference_reader import DebateRef


def _make_ref(tmp_path: Path, ticker: str = "XOM", sector: str = "Energy") -> DebateRef:
    ticker_dir = tmp_path / sector / ticker
    ticker_dir.mkdir(parents=True)
    debate = ticker_dir / "2026-07-03T12-00-00_000_mock_debate.md"
    debate.write_text(
        "# Debate — XOM (Energy)\n\n## Round 0\n\n### buffett\n- Verdict: BULLISH\n"
        "- Reasoning: solid moat, FCF compounding",
        encoding="utf-8",
    )
    meta_path = debate.with_name(debate.name.replace("_debate.md", "_meta.json"))
    meta_path.write_text(
        '{"ticker": "XOM", "sector": "Energy", "provider": "mock"}',
        encoding="utf-8",
    )
    return DebateRef(
        ticker=ticker,
        sector=sector,
        debate_path=debate,
        meta_path=meta_path,
        meta={"ticker": ticker, "sector": sector, "provider": "mock"},
        debate_mtime=debate.stat().st_mtime,
    )


def test_watch_summary_schema_valid() -> None:
    s = WatchSummary(
        moat="deep moat",
        cycle_phase="Operating Leverage",
        financial_health="FCF margin 15%",
        valuation="cheap vs sector",
        risks="cyclical demand | FX",
        providers_used="mock",
    )
    assert s.moat == "deep moat"
    assert s.providers_used == "mock"


def test_watch_summary_max_lengths_enforced() -> None:
    too_long = "x" * 250
    with pytest.raises(ValueError):
        WatchSummary(
            moat=too_long,
            cycle_phase="x",
            financial_health="x",
            valuation="x",
            risks="x",
        )


def test_aggregate_one_with_mock_returns_valid_summary(tmp_path: Path) -> None:
    ref = _make_ref(tmp_path)
    summary = aggregate_one("mock", ref, "XOM", "Energy")

    assert isinstance(summary, WatchSummary)
    assert summary.moat
    assert summary.cycle_phase
    assert summary.financial_health
    assert summary.valuation
    assert summary.risks
    assert summary.providers_used == "mock"
    assert len(summary.moat) <= 200
    assert len(summary.risks) <= 400


def test_aggregate_one_retries_on_validation_error(tmp_path: Path) -> None:

    class FlakyMockModel:
        def __init__(self) -> None:
            self.calls = 0

        def with_structured_output(self, schema):
            return self

        def bind_tools(self, tools):
            return self

        def invoke(self, messages, config=None):
            self.calls += 1
            from app.watch.aggregator import WatchSummary
            if self.calls == 1:
                return SimpleBad()
            return WatchSummary(
                moat="retry success",
                cycle_phase="Operating Leverage",
                financial_health="healthy",
                valuation="fair",
                risks="none",
            )

    class SimpleBad:
        parsed = None
        text = "garbage"

    class FlakyProvider:
        def __init__(self) -> None:
            self._model = FlakyMockModel()

        def provider_name(self) -> str:
            return "flaky"

        def get_model(self):
            return self._model

    from app.providers import ProviderRegistry

    registry = ProviderRegistry._providers
    saved = registry.get("flaky")
    ProviderRegistry._providers["flaky"] = FlakyProvider()
    try:
        ref = _make_ref(tmp_path)
        summary = aggregate_one("flaky", ref, "XOM", "Energy")
        assert summary.moat == "retry success"
    finally:
        if saved is None:
            ProviderRegistry._providers.pop("flaky", None)
        else:
            ProviderRegistry._providers["flaky"] = saved


def test_aggregate_one_returns_placeholder_on_double_failure(tmp_path: Path) -> None:
    class AlwaysBadModel:
        def with_structured_output(self, schema):
            return self

        def bind_tools(self, tools):
            return self

        def invoke(self, messages, config=None):
            return SimpleNamespace(parsed=None, text="garbage")

    class AlwaysBadProvider:
        def __init__(self, model: AlwaysBadModel) -> None:
            self._model = model

        def provider_name(self) -> str:
            return "always_bad"

        def get_model(self):
            return self._model

    from types import SimpleNamespace

    from app.providers import ProviderRegistry

    model = AlwaysBadModel()
    ProviderRegistry._providers["always_bad"] = AlwaysBadProvider(model)
    try:
        ref = _make_ref(tmp_path)
        summary = aggregate_one("always_bad", ref, "XOM", "Energy")
        assert summary.moat == "Data unavailable"
        assert summary.cycle_phase == "Data unavailable"
        assert summary.risks == "Data unavailable"
        assert summary.providers_used == "always_bad"
    finally:
        ProviderRegistry._providers.pop("always_bad", None)


def test_aggregate_one_empty_debate_yields_placeholder(tmp_path: Path) -> None:
    from app.providers import ProviderRegistry

    registry = ProviderRegistry._providers
    saved = registry.get("mock")

    from tests._mock_provider import SchemaAwareMockProvider

    ProviderRegistry._providers["mock"] = SchemaAwareMockProvider()
    try:
        ticker_dir = tmp_path / "Energy" / "XOM"
        ticker_dir.mkdir(parents=True)
        debate = ticker_dir / "2026-07-03T12-00-00_000_mock_debate.md"
        debate.write_text("", encoding="utf-8")
        ref = DebateRef(
            ticker="XOM",
            sector="Energy",
            debate_path=debate,
            meta_path=None,
            meta={},
            debate_mtime=debate.stat().st_mtime,
        )
        summary = aggregate_one("mock", ref, "XOM", "Energy")
        assert summary.moat == "Data unavailable"
        assert summary.providers_used == "mock"
    finally:
        if saved is None:
            ProviderRegistry._providers.pop("mock", None)
        else:
            ProviderRegistry._providers["mock"] = saved
