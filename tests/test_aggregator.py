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
        moat="🟢 deep moat",
        cycle_phase="Operating Leverage",
        financial_health="FCF margin 15%",
        valuation="cheap vs sector",
        risks="cyclical demand | FX",
        providers_used="mock",
    )
    assert s.moat == "🟢 deep moat"
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
                moat="🟢 retry success",
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
        assert summary.moat == "🟢 retry success"
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
        from app.watch.aggregator import CyclePhase

        assert summary.moat == "🟡 Data unavailable for moat assessment"
        assert summary.cycle_phase == CyclePhase.CAPITAL_RETURN
        assert summary.risks == "Data unavailable for risk assessment"
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
        assert summary.moat == "🟡 Data unavailable for moat assessment"
        assert summary.providers_used == "mock"
    finally:
        if saved is None:
            ProviderRegistry._providers.pop("mock", None)
        else:
            ProviderRegistry._providers["mock"] = saved


def test_cycle_phase_enum_validation() -> None:
    from app.watch.aggregator import CyclePhase, WatchSummary

    s = WatchSummary(
        moat="🟢 test",
        cycle_phase=CyclePhase.CAPITAL_RETURN,
        financial_health="x",
        valuation="x",
        risks="x",
    )
    assert s.cycle_phase == CyclePhase.CAPITAL_RETURN
    assert s.cycle_phase.value == "Capital Return"


def test_moat_validator_rejects_no_emoji() -> None:
    from app.watch.aggregator import WatchSummary

    with pytest.raises(ValueError, match="moat must start"):
        WatchSummary(
            moat="Strong moat, widening",
            cycle_phase="Capital Return",
            financial_health="x",
            valuation="x",
            risks="x",
        )


def test_moat_validator_accepts_three_emojis() -> None:
    from app.watch.aggregator import WatchSummary

    for emoji in ["🟢", "🟡", "🔴"]:
        s = WatchSummary(
            moat=f"{emoji} test moat",
            cycle_phase="Capital Return",
            financial_health="x",
            valuation="x",
            risks="x",
        )
        assert s.moat.startswith(emoji)


def test_moat_validator_accepts_emoji_followed_by_punctuation() -> None:
    from app.watch.aggregator import WatchSummary

    s = WatchSummary(
        moat="🟢. Test moat",
        cycle_phase="Capital Return",
        financial_health="x",
        valuation="x",
        risks="x",
    )
    assert s.moat == "🟢. Test moat"


def test_fundamentals_block_in_user_message() -> None:
    from app.watch.aggregator import _build_messages

    msgs = _build_messages(
        "XOM",
        "Energy",
        "# debate text",
        fundamentals={"FCF yield": 0.064, "EV/EBITDA": None, "Price": 114.5},
    )
    user_msg = msgs[1]["content"]
    assert "Fundamentals snapshot" in user_msg
    assert "FCF yield: 6.4%" in user_msg
    assert "EV/EBITDA: n/a" in user_msg
    assert "Price: 114.50" in user_msg


def test_fundamentals_block_absent_when_none() -> None:
    from app.watch.aggregator import _build_messages

    msgs = _build_messages("XOM", "Energy", "# debate", fundamentals=None)
    user_msg = msgs[1]["content"]
    assert "Fundamentals snapshot" not in user_msg


def test_placeholder_summary_starts_with_emoji() -> None:
    from app.watch.aggregator import _placeholder_summary

    p = _placeholder_summary(provider_name="mock")
    assert p.moat[0] in "🟢🟡🔴"
    assert p.cycle_phase.value == "Capital Return"


def test_do_not_block_present_in_system_message() -> None:
    from app.watch.aggregator import _build_messages

    msgs = _build_messages("XOM", "Energy", "# debate")
    sys_msg = msgs[0]["content"]
    for phrase in [
        "DO NOT",
        "hedge language",
        "invent numbers",
        "numbered lists",
        "comment on the debate",
        "buy/sell recommendations",
        "disclaimers",
        "every bullet with the company name",
        "negation hedges",
        "stack synonyms",
        "filler connectors",
        "pad with generic language",
    ]:
        assert phrase in sys_msg, f"Missing phrase: {phrase}"


def test_example_block_present_in_system_message() -> None:
    from app.watch.aggregator import _build_messages

    msgs = _build_messages("XOM", "Energy", "# debate")
    sys_msg = msgs[0]["content"]
    assert "<example>" in sys_msg
    assert "Capital Return" in sys_msg
    assert "🟢" in sys_msg
    assert "P/FCF" in sys_msg


def test_aggregate_one_accepts_fundamentals_kwarg() -> None:
    import inspect

    from app.watch.aggregator import aggregate_one

    sig = inspect.signature(aggregate_one)
    assert "fundamentals" in sig.parameters


def test_aggregate_one_uses_mock_provider_with_fundamentals(tmp_path: Path) -> None:
    from app.providers import ProviderRegistry
    from tests._mock_provider import SchemaAwareMockProvider

    saved = ProviderRegistry._providers.get("mock")
    ProviderRegistry._providers["mock"] = SchemaAwareMockProvider()
    try:
        ref = _make_ref(tmp_path)
        fundamentals = {"FCF yield": 0.064, "Net Debt/EBITDA": 0.39, "Price": 114.5}
        summary = aggregate_one(
            "mock", ref, "XOM", "Energy", fundamentals=fundamentals
        )
        assert summary.moat.startswith("🟢")
        from app.watch.aggregator import CyclePhase

        assert summary.cycle_phase in CyclePhase
        assert summary.providers_used == "mock"
    finally:
        if saved is None:
            ProviderRegistry._providers.pop("mock", None)
        else:
            ProviderRegistry._providers["mock"] = saved
