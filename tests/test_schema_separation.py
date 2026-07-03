from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest

from app.debate.engine import (
    _SCHEMA_DEFAULTS,
    LLM_INPUT_SCHEMA,
    _condense_thesis,
    _invoke_with_fallback,
    build_rebuttal_messages,
    run_debate,
)
from app.models import (
    DebateResult,
    Direction,
    Domain,
    Rebuttal,
    RebuttalInput,
    Thesis,
    ThesisInput,
    Verdict,
    _coerce_direction,
)
from app.providers import LLMProvider, ProviderRegistry


def test_thesis_input_has_three_required_fields() -> None:
    required = set(ThesisInput.model_json_schema()["required"])
    assert required == {"verdict", "conviction", "reasoning"}, (
        f"expected 3 required fields, got {required}"
    )


def test_rebuttal_input_has_three_required_fields() -> None:
    required = set(RebuttalInput.model_json_schema()["required"])
    assert required == {"revised_verdict", "revised_conviction", "reasoning"}, (
        f"expected 3 required fields, got {required}"
    )


def test_thesis_input_is_slimmer_than_thesis() -> None:
    full_required = set(Thesis.model_json_schema()["required"])
    slim_required = set(ThesisInput.model_json_schema()["required"])
    assert len(slim_required) < len(full_required)
    assert slim_required.issubset(full_required)
    assert {"agent_id", "target", "domain", "round"}.isdisjoint(slim_required)


def test_rebuttal_input_is_slimmer_than_rebuttal() -> None:
    full_required = set(Rebuttal.model_json_schema()["required"])
    slim_required = set(RebuttalInput.model_json_schema()["required"])
    assert len(slim_required) < len(full_required)
    assert slim_required.issubset(full_required)
    assert {"agent_id", "target", "domain", "round"}.isdisjoint(slim_required)


def test_llm_input_schema_maps_thesis_and_rebuttal_to_slim() -> None:
    assert LLM_INPUT_SCHEMA["Thesis"] is ThesisInput
    assert LLM_INPUT_SCHEMA["Rebuttal"] is RebuttalInput
    assert "Verdict" not in LLM_INPUT_SCHEMA


def test_coerce_direction_extracts_from_sentence() -> None:
    assert _coerce_direction("NEUTRAL with conviction 0.50") == "NEUTRAL"
    assert _coerce_direction("I am BEARISH on this") == "BEARISH"
    assert _coerce_direction("the view is bullish here") == "BULLISH"
    assert _coerce_direction("BULLISH") == "BULLISH"
    assert _coerce_direction("bearish") == "BEARISH"
    assert _coerce_direction(None) == "NEUTRAL"
    assert _coerce_direction(42) == "NEUTRAL"
    assert _coerce_direction(Direction.BEARISH) == "BEARISH"
    assert _coerce_direction("totally unrelated string") == "NEUTRAL"


def test_thesis_validates_with_sentence_enum() -> None:
    t = Thesis(
        agent_id="buffett",
        target="JPM",
        domain=Domain.COMPANY,
        round=0,
        verdict="NEUTRAL with conviction 0.50",
        conviction=0.5,
        reasoning="real reasoning",
    )
    assert t.verdict == Direction.NEUTRAL
    assert t.reasoning == "real reasoning"


def test_thesis_input_validates_with_sentence_enum() -> None:
    t = ThesisInput(
        verdict="BEARISH on balance",
        conviction=0.4,
        reasoning="real reasoning",
    )
    assert t.verdict == Direction.BEARISH


def test_rebuttal_validates_with_sentence_enum() -> None:
    rb = Rebuttal(
        agent_id="taleb",
        target="JPM",
        domain=Domain.COMPANY,
        round=1,
        revised_verdict="the view is bullish here",
        revised_conviction=0.6,
        reasoning="real rebuttal",
    )
    assert rb.revised_verdict == Direction.BULLISH


def test_rebuttal_input_validates_with_sentence_enum() -> None:
    rb = RebuttalInput(
        revised_verdict="I am BEARISH on this",
        revised_conviction=0.3,
        reasoning="real rebuttal",
    )
    assert rb.revised_verdict == Direction.BEARISH


def test_rebuttal_message_uses_condensed_theses() -> None:
    theses = [
        Thesis(
            agent_id=f"persona_{i}",
            target="AAPL",
            domain=Domain.COMPANY,
            round=0,
            verdict=Direction.BULLISH if i % 2 == 0 else Direction.BEARISH,
            conviction=0.6,
            key_drivers=[f"driver_{i}_a", f"driver_{i}_b", f"driver_{i}_c"],
            reasoning="lorem ipsum " * 400,
            data_used=["data"],
        )
        for i in range(3)
    ]
    msgs = build_rebuttal_messages(
        persona_id="taleb",
        target="AAPL",
        domain="company",
        target_date=date(2026, 7, 2),
        context_md="FY24 P/E 22.",
        prior_theses=theses,
    )
    user_msg = msgs[-1]["content"]
    assert "drivers:" in user_msg
    assert "reasoning excerpt:" in user_msg
    full_text = " ".join(t.reasoning for t in theses)
    assert full_text not in user_msg
    assert len(user_msg) < 8000


def test_condense_thesis_breaks_at_sentence_boundary() -> None:
    t = Thesis(
        agent_id="buffett",
        target="AAPL",
        domain=Domain.COMPANY,
        round=0,
        verdict=Direction.BULLISH,
        conviction=0.7,
        key_drivers=["d1"],
        reasoning="First sentence. Second sentence. " + ("x" * 500),
        data_used=[],
    )
    condensed = _condense_thesis(t, excerpt_chars=120)
    assert "…" in condensed
    assert "Second sentence." in condensed
    assert condensed.startswith("- **buffett**")


def test_schema_defaults_include_slim_inputs() -> None:
    assert "ThesisInput" in _SCHEMA_DEFAULTS
    assert "RebuttalInput" in _SCHEMA_DEFAULTS
    for key in ("agent_id", "target", "domain", "round"):
        assert key not in _SCHEMA_DEFAULTS["ThesisInput"], (
            f"slim ThesisInput defaults must not contain id-field {key}"
        )
        assert key not in _SCHEMA_DEFAULTS["RebuttalInput"], (
            f"slim RebuttalInput defaults must not contain id-field {key}"
        )


class _HostileMinimaxMockModel:
    """Simulates the MiniMax-M3 intermittent failure pattern:

    * include_raw=True raises TypeError (some Anthropic-compatible endpoints)
    * plain with_structured_output also raises (MiniMax tool-call bug)
    * plain invoke returns JSON with sentence-enum verdict (real failure)
    * ~20% of the time, plain invoke also raises (total failure → L3)
    """

    _counter: dict[str, int] = {"n": 0}

    def __init__(
        self,
        schema: Any = None,
    ) -> None:
        self._schema = schema

    def with_structured_output(self, schema: Any, **kw: Any) -> _HostileMinimaxMockModel:
        return _HostileMinimaxMockModel(schema)

    def bind_tools(self, tools: Any) -> _HostileMinimaxMockModel:
        return self

    def invoke(self, messages: Any, config: Any = None) -> Any:
        _HostileMinimaxMockModel._counter["n"] += 1
        n = _HostileMinimaxMockModel._counter["n"]
        if n % 7 == 0:
            raise RuntimeError("simulated intermittent MiniMax failure")
        s = self._schema
        if s is Thesis or s is ThesisInput:
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "verdict": "BULLISH with conviction 0.70",
                        "conviction": 0.7,
                        "reasoning": (
                            "Concrete pillar-by-pillar analysis citing data: "
                            "P/E 22 vs 10y median 18, FCF $80B, net cash $30B."
                        ),
                        "key_drivers": ["P/E compression", "FCF base"],
                        "data_used": ["P/E", "FCF"],
                    }
                )
            )
        if s is Rebuttal or s is RebuttalInput:
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "revised_verdict": "NEUTRAL given the rebuttals",
                        "revised_conviction": 0.5,
                        "reasoning": (
                            "Walking the 6 pillars: Taleb's tail-risk reading is "
                            "valid for the credit book; Buffet's moat argument "
                            "stands. Net: neutral."
                        ),
                        "targets": ["taleb", "buffett"],
                        "concessions": ["buffett's moat is real"],
                        "disagreements": ["taleb's tail is overstated"],
                    }
                )
            )
        if s is Verdict:
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "final_call": "Split bull/bear",
                        "summary": "Hostile mock synthesis.",
                        "confidence": 0.55,
                        "points_of_agreement": ["moat exists"],
                        "points_of_disagreement": ["valuation"],
                    }
                )
            )
        msg = messages[-1]["content"] if messages else ""
        lower = msg.lower()
        if "rebuttal" in lower or "targets" in lower or "concessions" in lower:
            return SimpleNamespace(
                content=json.dumps(
                    {
                        "revised_verdict": "NEUTRAL given the rebuttals",
                        "revised_conviction": 0.5,
                        "reasoning": (
                            "Walking the 6 pillars: Taleb's tail-risk reading is "
                            "valid for the credit book; Buffet's moat argument "
                            "stands. Net: neutral."
                        ),
                        "targets": ["taleb", "buffett"],
                        "concessions": ["buffett's moat is real"],
                        "disagreements": ["taleb's tail is overstated"],
                    }
                )
            )
        return SimpleNamespace(
            content=json.dumps(
                {
                    "verdict": "BULLISH with conviction 0.70",
                    "conviction": 0.7,
                    "reasoning": (
                        "Concrete pillar-by-pillar analysis citing data: "
                        "P/E 22 vs 10y median 18, FCF $80B, net cash $30B."
                    ),
                    "key_drivers": ["P/E compression", "FCF base"],
                    "data_used": ["P/E", "FCF"],
                }
            )
        )


class _HostileMinimaxMockProvider(LLMProvider):
    def provider_name(self) -> str:
        return "mock"

    def get_model(self) -> _HostileMinimaxMockModel:
        _HostileMinimaxMockModel._counter["n"] = 0
        return _HostileMinimaxMockModel()


ALL_PERSONAS = [
    "buffett", "lynch", "dalio", "burry", "greenspan",
    "bernanke", "volcker", "dimon", "eisman", "grantham",
    "simons", "taleb", "wood", "gundlach", "thaler",
]


@pytest.fixture
def hostile_minimax_provider() -> None:
    ProviderRegistry.register("mock", _HostileMinimaxMockProvider())
    yield
    ProviderRegistry._providers.pop("mock", None)


def test_debate_no_drop_with_hostile_minimax_mock(hostile_minimax_provider) -> None:
    result = run_debate(
        analysts=ALL_PERSONAS,
        target="JPM",
        domain="company",
        target_date=date(2026, 7, 2),
        context_md="FY24 P/E 22, FCF $80B, net cash $30B.",
        rounds=2,
        provider_name="mock",
        include_synthesis=True,
    )
    assert isinstance(result, DebateResult)
    assert len(result.theses) == 15, (
        f"expected 15 theses, got {len(result.theses)}"
    )
    assert len(result.rebuttals) == 15, (
        f"expected 15 rebuttals, got {len(result.rebuttals)}"
    )
    assert result.verdict is not None

    for t in result.theses:
        assert t.reasoning != "[unavailable]", (
            f"thesis {t.agent_id} fell back to L3 default"
        )
        assert len(t.reasoning) > 30, (
            f"thesis {t.agent_id} reasoning too short: {t.reasoning!r}"
        )

    for r in result.rebuttals:
        assert r.reasoning != "[unavailable]", (
            f"rebuttal {r.agent_id} fell back to L3 default — sentence-enum coercion should have caught this"
        )
        assert len(r.reasoning) > 30, (
            f"rebuttal {r.agent_id} reasoning too short: {r.reasoning!r}"
        )


def test_invoke_with_fallback_promotes_thesisinput_to_thesis() -> None:
    class _SlimThesisModel:
        def with_structured_output(self, schema, **kw):
            return self

        def bind_tools(self, tools):
            return self

        def invoke(self, messages, config=None):
            return ThesisInput(
                verdict=Direction.BEARISH,
                conviction=0.4,
                reasoning="real",
                key_drivers=["d"],
                data_used=["x"],
            )

    class _SlimProvider(LLMProvider):
        def provider_name(self):
            return "mock"

        def get_model(self):
            return _SlimThesisModel()

    result = _invoke_with_fallback(_SlimProvider(), Thesis, [{"role": "user", "content": "x"}])
    assert isinstance(result, Thesis)
    assert result.verdict == Direction.BEARISH
    assert result.reasoning == "real"
    assert result.agent_id == "[unavailable]"
    assert result.data_used == ["x"]


def test_invoke_with_fallback_handles_sentence_enum_in_l2() -> None:
    class _SentenceEnumModel:
        def with_structured_output(self, schema, **kw):
            raise TypeError("no include_raw")

        def bind_tools(self, tools):
            return self

        def invoke(self, messages, config=None):
            return SimpleNamespace(content=json.dumps({
                "verdict": "BEARISH given the risks",
                "conviction": 0.3,
                "reasoning": "real",
                "key_drivers": ["d"],
                "data_used": [],
            }))

    class _SentenceEnumProvider(LLMProvider):
        def provider_name(self):
            return "mock"

        def get_model(self):
            return _SentenceEnumModel()

    result = _invoke_with_fallback(
        _SentenceEnumProvider(), Thesis, [{"role": "user", "content": "x"}]
    )
    assert isinstance(result, Thesis)
    assert result.verdict == Direction.BEARISH
    assert result.reasoning == "real"
