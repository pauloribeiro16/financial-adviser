from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest

from app.debate import engine
from app.debate.engine import _invoke_with_fallback, run_debate
from app.models import (
    DebateResult,
    Direction,
    Domain,
    Rebuttal,
    Thesis,
    Verdict,
)
from app.providers import LLMProvider, ProviderRegistry


def _thesis_provider_with_structured(structured_factory):
    class _M:
        def __init__(self, schema=None) -> None:
            self._schema = schema

        def with_structured_output(self, schema, **kw):
            return structured_factory(schema, kw)

        def bind_tools(self, tools):
            return self

        def invoke(self, messages, config=None):
            return SimpleNamespace(content="plain text fallback")

    class _P(LLMProvider):
        def provider_name(self):
            return "mock"

        def get_model(self):
            return _M()

    return _P()


class _SchemaOkMockModel:
    """Returns a real Thesis from ``with_structured_output(include_raw=True)``.

    The dict shape mirrors LangChain's ``include_raw=True`` contract:
    ``{"raw": ..., "parsed": <Thesis>, "parsing_error": None}``.
    """

    def __init__(self, schema=None) -> None:
        self._schema = schema

    def with_structured_output(self, schema, **kw):
        return _SchemaOkMockModel(schema)

    def bind_tools(self, tools):
        return self

    def invoke(self, messages, config=None):
        return {
            "raw": SimpleNamespace(content="ok"),
            "parsed": Thesis(
                agent_id="buffett",
                target="AAPL",
                domain=Domain.COMPANY,
                round=0,
                verdict=Direction.BULLISH,
                conviction=0.7,
                key_drivers=["d1", "d2"],
                reasoning="ok reasoning",
                data_used=["ctx"],
            ),
            "parsing_error": None,
        }


class _SchemaOkMockProvider(LLMProvider):
    def provider_name(self):
        return "mock"

    def get_model(self):
        return _SchemaOkMockModel()


@pytest.fixture
def schema_ok_provider():
    ProviderRegistry.register("mock", _SchemaOkMockProvider())
    yield
    ProviderRegistry._providers.pop("mock", None)


class _HostileStructuredMockModel:
    """L1 always raises; L2 returns JSON text; no include_raw support."""

    def __init__(self, schema=None) -> None:
        self._schema = schema

    def with_structured_output(self, schema, **kw):
        raise TypeError("include_raw not supported by hostile mock")

    def bind_tools(self, tools):
        return self

    def invoke(self, messages, config=None):
        return SimpleNamespace(
            content=json.dumps(
                {
                    "verdict": "BULLISH",
                    "conviction": 0.7,
                    "reasoning": "ok",
                    "key_drivers": ["d1"],
                    "data_used": ["ctx"],
                }
            )
        )


class _HostileStructuredMockProvider(LLMProvider):
    def provider_name(self):
        return "mock"

    def get_model(self):
        return _HostileStructuredMockModel()


@pytest.fixture
def hostile_provider():
    ProviderRegistry.register("mock", _HostileStructuredMockProvider())
    yield
    ProviderRegistry._providers.pop("mock", None)


class _HostilePartialJsonMockModel:
    """L1 raises; L2 returns JSON missing 'reasoning'."""

    def __init__(self, schema=None) -> None:
        self._schema = schema

    def with_structured_output(self, schema, **kw):
        raise TypeError("include_raw not supported by hostile mock")

    def bind_tools(self, tools):
        return self

    def invoke(self, messages, config=None):
        return SimpleNamespace(
            content=json.dumps(
                {
                    "verdict": "BEARISH",
                    "conviction": 0.3,
                    "key_drivers": ["only driver"],
                }
            )
        )


class _HostilePartialJsonMockProvider(LLMProvider):
    def provider_name(self):
        return "mock"

    def get_model(self):
        return _HostilePartialJsonMockModel()


@pytest.fixture
def hostile_partial_provider():
    ProviderRegistry.register("mock", _HostilePartialJsonMockProvider())
    yield
    ProviderRegistry._providers.pop("mock", None)


class _HostileGarbageMockModel:
    """L1 raises; L2 returns plain English text (no JSON)."""

    def __init__(self, schema=None) -> None:
        self._schema = schema

    def with_structured_output(self, schema, **kw):
        raise TypeError("include_raw not supported by hostile mock")

    def bind_tools(self, tools):
        return self

    def invoke(self, messages, config=None):
        return SimpleNamespace(
            content="I cannot provide a structured response at this time."
        )


class _HostileGarbageMockProvider(LLMProvider):
    def provider_name(self):
        return "mock"

    def get_model(self):
        return _HostileGarbageMockModel()


@pytest.fixture
def hostile_garbage_provider():
    ProviderRegistry.register("mock", _HostileGarbageMockProvider())
    yield
    ProviderRegistry._providers.pop("mock", None)


class _TotalFailureMockModel:
    """L1 raises; L2 raises. Forces L3 defaults."""

    def __init__(self, schema=None) -> None:
        self._schema = schema

    def with_structured_output(self, schema, **kw):
        raise TypeError("include_raw not supported by hostile mock")

    def bind_tools(self, tools):
        return self

    def invoke(self, messages, config=None):
        raise RuntimeError("simulated total LLM failure")


class _TotalFailureMockProvider(LLMProvider):
    def provider_name(self):
        return "mock"

    def get_model(self):
        return _TotalFailureMockModel()


@pytest.fixture
def total_failure_provider():
    ProviderRegistry.register("mock", _TotalFailureMockProvider())
    yield
    ProviderRegistry._providers.pop("mock", None)


def test_l1_success(schema_ok_provider) -> None:
    msgs = [{"role": "user", "content": "go"}]
    result = _invoke_with_fallback(_SchemaOkMockProvider(), Thesis, msgs)
    assert isinstance(result, Thesis)
    assert result.verdict == Direction.BULLISH
    assert result.conviction == pytest.approx(0.7)


def test_l1_raises_falls_through_to_l2(hostile_provider) -> None:
    msgs = [{"role": "user", "content": "go"}]
    result = _invoke_with_fallback(_HostileStructuredMockProvider(), Thesis, msgs)
    assert isinstance(result, Thesis)
    assert result.verdict == Direction.BULLISH
    assert result.conviction == pytest.approx(0.7)
    assert result.reasoning == "ok"
    assert result.key_drivers == ["d1"]


def test_l2_partial_dict_filled_with_defaults(hostile_partial_provider) -> None:
    msgs = [{"role": "user", "content": "go"}]
    result = _invoke_with_fallback(_HostilePartialJsonMockProvider(), Thesis, msgs)
    assert isinstance(result, Thesis)
    assert result.verdict == Direction.BEARISH
    assert result.conviction == pytest.approx(0.3)
    assert result.reasoning == "[unavailable]"
    assert result.key_drivers == ["only driver"]
    assert result.data_used == []


def test_l2_garbage_text_falls_through_to_l3(hostile_garbage_provider) -> None:
    msgs = [{"role": "user", "content": "go"}]
    result = _invoke_with_fallback(_HostileGarbageMockProvider(), Thesis, msgs)
    assert isinstance(result, Thesis)
    assert result.verdict == Direction.NEUTRAL
    assert result.conviction == pytest.approx(0.5)
    assert result.reasoning == "[unavailable]"
    assert result.key_drivers == []
    assert result.data_used == []


def test_l3_logs_warning(total_failure_provider, monkeypatch) -> None:
    msgs = [{"role": "user", "content": "go"}]
    captured: list[tuple[str, dict]] = []

    class _CapturingLog:
        def debug(self, event: str, **kw: Any) -> None:
            captured.append((event, kw))

        def info(self, event: str, **kw: Any) -> None:
            captured.append((event, kw))

        def warning(self, event: str, **kw: Any) -> None:
            captured.append((event, kw))

        def error(self, event: str, **kw: Any) -> None:
            captured.append((event, kw))

    monkeypatch.setattr(engine, "log", _CapturingLog())
    result = _invoke_with_fallback(_TotalFailureMockProvider(), Thesis, msgs)
    assert isinstance(result, Thesis)
    assert result.verdict == Direction.NEUTRAL
    level3 = [
        (ev, kw) for ev, kw in captured
        if ev == "debate.invoke.fallback_used" and kw.get("level") == 3
    ]
    assert level3, f"expected level=3 fallback_used log event, got {captured}"


ALL_PERSONAS = [
    "buffett", "lynch", "dalio", "burry", "greenspan",
    "bernanke", "volcker", "dimon", "eisman", "grantham",
    "simons", "taleb", "wood", "gundlach", "thaler",
]


class _FullDebateHostileMockModel:
    """Full debate hostile mock.

    L1 (structured) always raises; L2 (plain invoke) returns a stub JSON
    payload with enough fields for each schema to construct.
    """

    def __init__(self, schema=None) -> None:
        self._schema = schema

    def with_structured_output(self, schema, **kw):
        raise TypeError("hostile: structured output unavailable")

    def bind_tools(self, tools):
        return self

    def invoke(self, messages, config=None):
        s = self._schema
        if s is Thesis:
            return SimpleNamespace(content=json.dumps(
                {
                    "verdict": "NEUTRAL",
                    "conviction": 0.5,
                    "reasoning": "[hostile mock thesis]",
                    "key_drivers": ["d"],
                    "data_used": ["ctx"],
                }
            ))
        if s is Rebuttal:
            return SimpleNamespace(content=json.dumps(
                {
                    "revised_verdict": "NEUTRAL",
                    "revised_conviction": 0.5,
                    "reasoning": "[hostile mock rebuttal]",
                    "targets": ["other"],
                    "concessions": ["c"],
                    "disagreements": ["d"],
                }
            ))
        if s is Verdict:
            return SimpleNamespace(content=json.dumps(
                {
                    "final_call": "neutral consensus",
                    "summary": "hostile mock synthesis",
                    "confidence": 0.5,
                    "points_of_agreement": ["a"],
                    "points_of_disagreement": [],
                }
            ))
        return SimpleNamespace(content="{}")


class _FullDebateHostileMockProvider(LLMProvider):
    def provider_name(self):
        return "mock"

    def get_model(self):
        return _FullDebateHostileMockModel()


@pytest.fixture
def full_debate_hostile_provider():
    ProviderRegistry.register("mock", _FullDebateHostileMockProvider())
    yield
    ProviderRegistry._providers.pop("mock", None)


def test_15_personas_never_dropped(full_debate_hostile_provider) -> None:
    result = run_debate(
        analysts=ALL_PERSONAS,
        target="AAPL",
        domain="company",
        target_date=date(2026, 7, 2),
        context_md="FY24 P/E 22, FCF $80B.",
        rounds=2,
        provider_name="mock",
        include_synthesis=True,
    )
    assert isinstance(result, DebateResult)
    assert len(result.theses) == 15, (
        f"expected 15 theses, got {len(result.theses)}: "
        f"{[t.agent_id for t in result.theses]}"
    )
    assert len(result.rebuttals) == 15, (
        f"expected 15 rebuttals, got {len(result.rebuttals)}"
    )
    assert result.verdict is not None
    assert isinstance(result.verdict, Verdict)
    assert {t.agent_id for t in result.theses} == set(ALL_PERSONAS)
    assert {r.agent_id for r in result.rebuttals} == set(ALL_PERSONAS)
