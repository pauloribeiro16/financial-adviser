from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.models import Assessment, Consensus, Direction, Domain, Rebuttal, Thesis, Verdict
from app.providers import LLMProvider
from app.watch.aggregator import WatchSummary


class SchemaAwareMockModel:
    """Mock LLM model that returns a valid Pydantic instance for whichever
    schema was requested via ``with_structured_output(...)``.

    Covers all four schemas used by the runtime (``Assessment``, ``Thesis``,
    ``Rebuttal``, ``Verdict``) so the same provider works for both the legacy
    assessment path and the new debate path.
    """

    def __init__(self, schema: Any = None) -> None:
        self._schema = schema

    def with_structured_output(self, schema: Any) -> SchemaAwareMockModel:
        return SchemaAwareMockModel(schema)

    def bind_tools(self, tools: Any) -> SchemaAwareMockModel:
        return self

    def invoke(self, messages: list[dict[str, str]], config: Any = None) -> Any:
        s = self._schema
        if s is Assessment:
            preview = (messages[-1]["content"] if messages else "")[:60].replace("\n", " ")
            return SimpleNamespace(
                diagnosis=f"[MOCK diagnosis based on: {preview}...]",
                outlook="[MOCK] Outlook: NEUTRAL, awaiting data.",
                key_drivers=["mock driver 1", "mock driver 2", "mock driver 3"],
                news_interpretation="[MOCK] No material news in scope.",
                reasoning_trace="[MOCK] Reasoning trace: placeholder for testing.",
                signal_direction="NEUTRAL",
                signal_strength=0.5,
            )
        if s is Thesis:
            return Thesis(
                agent_id="mock",
                target="MOCK",
                domain=Domain.MACRO,
                round=0,
                verdict=Direction.NEUTRAL,
                conviction=0.5,
                key_drivers=["mock driver a", "mock driver b"],
                reasoning="[MOCK thesis] placeholder reasoning.",
                data_used=["mock data point"],
            )
        if s is Rebuttal:
            return Rebuttal(
                agent_id="mock",
                target="MOCK",
                domain=Domain.MACRO,
                round=1,
                targets=["other"],
                concessions=["mock concession"],
                disagreements=["mock disagreement"],
                revised_verdict=Direction.NEUTRAL,
                revised_conviction=0.5,
                reasoning="[MOCK rebuttal] placeholder reasoning.",
            )
        if s is Verdict:
            return Verdict(
                target="MOCK",
                domain=Domain.MACRO,
                consensus=Consensus.NEUTRAL,
                bull_count=0,
                bear_count=0,
                neutral_count=2,
                avg_conviction=0.5,
                points_of_agreement=["mock agreement"],
                points_of_disagreement=[],
                final_call="[MOCK] Neutral consensus",
                confidence=0.5,
                summary="[MOCK] Summary of debate.",
            )
        if s is WatchSummary:
            return WatchSummary(
                moat="[MOCK] Deep moat widening — 3 green dots.",
                cycle_phase="[MOCK] Operating Leverage phase.",
                financial_health="[MOCK] Net debt 1.2x EBITDA, FCF margin 18%.",
                valuation="[MOCK] Fair at 12x P/FCF vs sector 14x.",
                risks="[MOCK] Cyclical demand | FX drag | Regulatory.",
                providers_used="mock",
            )
        return SimpleNamespace(text="[MOCK] unknown schema")


class SchemaAwareMockProvider(LLMProvider):
    def provider_name(self) -> str:
        return "mock"

    def get_model(self) -> SchemaAwareMockModel:
        return SchemaAwareMockModel()
