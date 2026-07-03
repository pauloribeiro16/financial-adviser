from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest

from app.debate import engine
from app.debate.orchestrator import orchestrate_debate
from app.debate.tracing import DebateTrace, _NoopHandler
from app.models import (
    Consensus,
    Direction,
    Domain,
    Rebuttal,
    Thesis,
    Verdict,
)
from app.providers import LLMProvider, ProviderRegistry


class _RecordingMockModel:
    """Mock LLM that returns a valid Pydantic instance for whichever schema
    was requested AND records every ``config`` dict passed to ``invoke``.

    The ``captured_configs`` list lets tests assert that ``engine._invoke_structured``
    injected the Langfuse CallbackHandler into ``config['callbacks']``. A shared
    list is held at the class level so ``with_structured_output`` returning a
    new wrapper still writes to the same list.
    """

    _shared_configs: list[Any] = []

    def __init__(self, schema: Any = None) -> None:
        self._schema = schema

    def with_structured_output(self, schema: Any) -> _RecordingMockModel:
        return _RecordingMockModel(schema)

    def bind_tools(self, tools: Any) -> _RecordingMockModel:
        return self

    def invoke(self, messages: list[dict[str, str]], config: Any = None) -> Any:
        type(self)._shared_configs.append(config)
        s = self._schema
        if s is Thesis:
            return Thesis(
                agent_id="rec",
                target="AAPL",
                domain=Domain.COMPANY,
                round=0,
                verdict=Direction.BULLISH,
                conviction=0.6,
                key_drivers=["mock driver a", "mock driver b"],
                reasoning="[MOCK thesis] placeholder reasoning.",
                data_used=["P/E"],
            )
        if s is Rebuttal:
            return Rebuttal(
                agent_id="rec",
                target="AAPL",
                domain=Domain.COMPANY,
                round=1,
                targets=["other"],
                concessions=["c"],
                disagreements=["d"],
                revised_verdict=Direction.NEUTRAL,
                revised_conviction=0.5,
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
                avg_conviction=0.55,
                points_of_agreement=["both like the moat"],
                points_of_disagreement=[],
                final_call="[MOCK] Split bull consensus",
                confidence=0.55,
                summary="[MOCK] Summary of debate.",
            )
        return SimpleNamespace(text="[MOCK] unknown schema")


class _RecordingMockProvider(LLMProvider):
    """Provider whose ``get_model()`` returns a single shared recording model
    so all ``invoke`` calls land in the same shared configs list."""

    def __init__(self) -> None:
        self._model = _RecordingMockModel()

    def provider_name(self) -> str:
        return "mock"

    def get_model(self) -> _RecordingMockModel:
        return self._model


@pytest.fixture
def recording_mock():
    _RecordingMockModel._shared_configs = []
    saved = ProviderRegistry._providers.get("mock")
    provider = _RecordingMockProvider()
    ProviderRegistry.register("mock", provider)
    yield provider
    if saved is not None:
        ProviderRegistry._providers["mock"] = saved
    else:
        ProviderRegistry._providers.pop("mock", None)
        ProviderRegistry.initialize_defaults()


@pytest.fixture
def fake_langfuse_keys(monkeypatch: pytest.MonkeyPatch):
    """Set LANGFUSE_* env vars so DebateTrace() enables and instantiates a real
    ``CallbackHandler`` from the installed SDK (no manual stubbing — v4.11.0
    accepts any non-empty public/secret pair without raising)."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    yield


def test_debate_trace_disabled_without_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    trace = DebateTrace()
    assert trace.enabled is False
    assert isinstance(trace.callback, _NoopHandler)
    with trace.attributes(session_id="s", tags=["t"]) as h:
        assert isinstance(h, _NoopHandler)


def test_debate_trace_enabled_with_env_vars(fake_langfuse_keys: None) -> None:
    trace = DebateTrace()
    assert trace.enabled is True
    from langfuse.langchain import CallbackHandler

    assert isinstance(trace.callback, CallbackHandler)


def test_handler_is_wired_into_every_invoke(
    fake_langfuse_keys: None,
    recording_mock: _RecordingMockProvider,
) -> None:
    """With LANGFUSE_* set, every ``structured.invoke(messages, config=cfg)``
    inside the engine must receive a config dict whose ``callbacks`` list
    contains the Langfuse ``CallbackHandler``."""
    from langfuse.langchain import CallbackHandler

    trace = DebateTrace()
    orchestrate_debate(
        analysts=["buffett", "taleb"],
        target="AAPL",
        domain="company",
        target_date=date(2025, 3, 31),
        rounds=2,
        provider_name="mock",
        include_synthesis=True,
        session_id="test-session",
        trace=trace,
        ctx={
            "ticker": "AAPL",
            "edgar": {"submissions": {}, "latest_10k": None, "facts": {}},
            "quote": {"price": 200.0, "previous_close": 198.0},
            "fundamentals": {},
        },
    )

    assert _RecordingMockModel._shared_configs, "no invokes were captured"
    for cfg in _RecordingMockModel._shared_configs:
        assert cfg is not None, "config should not be None when callback is set"
        assert "callbacks" in cfg, f"callbacks key missing in cfg={cfg!r}"
        assert len(cfg["callbacks"]) >= 1, f"callbacks list empty in cfg={cfg!r}"
        assert any(isinstance(cb, CallbackHandler) for cb in cfg["callbacks"]), (
            f"no CallbackHandler in callbacks for cfg={cfg!r}"
        )


def test_propagate_attributes_called_with_session_and_tags(
    fake_langfuse_keys: None,
    recording_mock: _RecordingMockProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """orchestrate_debate must apply ``propagate_attributes(session_id=..., tags=...)``
    via ``DebateTrace.attributes(...)`` so the active Langfuse trace picks up
    the session and tags."""
    captured: list[dict[str, Any]] = []

    def fake_propagate_attributes(**kw: Any) -> Any:
        captured.append(kw)
        from contextlib import contextmanager

        @contextmanager
        def _cm():
            yield None

        return _cm()

    monkeypatch.setattr("langfuse.propagate_attributes", fake_propagate_attributes)

    trace = DebateTrace()
    orchestrate_debate(
        analysts=["buffett", "taleb"],
        target="AAPL",
        domain="company",
        target_date=date(2025, 3, 31),
        rounds=2,
        provider_name="mock",
        include_synthesis=True,
        session_id="test-session",
        trace=trace,
        ctx={
            "ticker": "AAPL",
            "edgar": {"submissions": {}, "latest_10k": None, "facts": {}},
            "quote": {"price": 200.0, "previous_close": 198.0},
            "fundamentals": {},
        },
    )

    assert captured, "propagate_attributes was never called"
    seen_kwargs = {tuple(sorted(kw.keys())): kw for kw in captured}
    matched = next(
        (kw for kw in captured if kw.get("session_id") == "test-session"),
        None,
    )
    assert matched is not None, (
        f"no propagate_attributes call with session_id='test-session' in {seen_kwargs!r}"
    )
    tags = matched.get("tags") or []
    assert "domain:company" in tags, f"missing 'domain:company' tag in {tags!r}"
    assert "analyst:buffett" in tags, f"missing 'analyst:buffett' tag in {tags!r}"
    assert "analyst:taleb" in tags, f"missing 'analyst:taleb' tag in {tags!r}"
    assert matched.get("metadata"), f"metadata should be populated, got {matched!r}"
    assert matched.get("trace_name") == "debate.company.AAPL", (
        f"trace_name should be 'debate.company.AAPL', got {matched.get('trace_name')!r}"
    )


def test_graceful_degradation_without_env_vars(
    monkeypatch: pytest.MonkeyPatch,
    recording_mock: _RecordingMockProvider,
) -> None:
    """Without LANGFUSE_* env vars the whole debate pipeline still completes
    cleanly, DebateTrace().enabled is False, and no exception escapes."""
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    trace = DebateTrace()
    assert trace.enabled is False
    assert isinstance(trace.callback, _NoopHandler)

    captured: list[dict[str, Any]] = []

    def fake_propagate_attributes(**kw: Any) -> Any:
        captured.append(kw)
        from contextlib import contextmanager

        @contextmanager
        def _cm():
            yield None

        return _cm()

    monkeypatch.setattr("langfuse.propagate_attributes", fake_propagate_attributes)

    result = orchestrate_debate(
        analysts=["buffett", "taleb"],
        target="AAPL",
        domain="company",
        target_date=date(2025, 3, 31),
        rounds=1,
        provider_name="mock",
        include_synthesis=True,
        session_id="noop-session",
        trace=trace,
        ctx={
            "ticker": "AAPL",
            "edgar": {"submissions": {}, "latest_10k": None, "facts": {}},
            "quote": {"price": 200.0, "previous_close": 198.0},
            "fundamentals": {},
        },
    )

    assert result.theses, "theses should be populated even without Langfuse"
    assert result.verdict is not None, "verdict should be populated"
    from langfuse.langchain import CallbackHandler
    for cfg in _RecordingMockModel._shared_configs:
        if cfg is None:
            continue
        for cb in cfg.get("callbacks", []):
            assert not isinstance(cb, CallbackHandler), (
                f"real CallbackHandler leaked into cfg={cfg!r} when Langfuse disabled"
            )
    assert captured == [], "propagate_attributes must NOT be called when disabled"


def test_engine_invoke_structured_accepts_callback() -> None:
    """Smoke check: ``engine._invoke_structured`` accepts a callback kwarg and
    appends it to ``config['callbacks']``."""

    class _Cb:
        pass

    cb = _Cb()
    captured: list[Any] = []

    class _M:
        def with_structured_output(self, schema: Any) -> _M:
            return self

        def bind_tools(self, tools: Any) -> _M:
            return self

        def invoke(self, messages: list[dict[str, str]], config: Any = None) -> Any:
            captured.append(config)
            return Thesis(
                agent_id="x",
                target="AAPL",
                domain=Domain.COMPANY,
                round=0,
                verdict=Direction.NEUTRAL,
                conviction=0.5,
                key_drivers=["k"],
                reasoning="r",
                data_used=["d"],
            )

    class _P(LLMProvider):
        def provider_name(self) -> str:
            return "mock"

        def get_model(self) -> _M:
            return _M()

    out = engine._invoke_structured(_P(), Thesis, [{"role": "user", "content": "x"}], None, cb)
    assert isinstance(out, Thesis)
    assert captured[0]["callbacks"] == [cb]
