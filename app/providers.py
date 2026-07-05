import os
from abc import ABC, abstractmethod
from types import SimpleNamespace

from langchain_anthropic import ChatAnthropic

from app.logging import get_logger

log = get_logger(__name__)


class LLMProvider(ABC):
    @abstractmethod
    def get_model(self): ...

    @abstractmethod
    def provider_name(self) -> str: ...


class MiniMaxProvider(LLMProvider):
    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str = "https://api.minimax.io/anthropic",
        temperature: float = 0.4,
    ):
        self.model = model or os.getenv("MINIMAX_MODEL", "MiniMax-M3")
        self.api_key = api_key if api_key is not None else os.getenv("MINIMAX_API_KEY", "")
        self.base_url = base_url
        self.temperature = temperature
        self._client: ChatAnthropic | None = None

    def provider_name(self) -> str:
        return f"minimax:{self.model}"

    def get_model(self) -> ChatAnthropic:
        if self._client is None:
            if not self.api_key:
                raise ValueError(
                    "MINIMAX_API_KEY is not set. Set the MINIMAX_API_KEY environment "
                    "variable (or pass api_key=...) before calling get_model()."
                )
            self._client = ChatAnthropic(
                model=self.model,
                api_key=self.api_key,
                anthropic_api_url=self.base_url,
                temperature=self.temperature,
            )
        return self._client


class MockModel:
    """Stand-in LLM model. Returns deterministic placeholder assessments.

    Suitable for tests and local development without network or API keys.
    """

    def __init__(self, schema=None) -> None:
        self._schema = schema

    def invoke(self, messages, config=None):
        user_content = messages[-1]["content"] if messages else ""
        preview = user_content[:60].replace("\n", " ")
        schema = self._schema
        if schema is not None and getattr(schema, "__name__", "") == "WatchSummary":
            from app.watch.aggregator import CyclePhase, WatchSummary

            return WatchSummary(
                moat="🟢 [MOCK] deep moat widening in serviceable markets",
                cycle_phase=CyclePhase.CAPITAL_RETURN,
                financial_health="[MOCK] FCF margin 12%, net debt 0.39x EBITDA",
                valuation="[MOCK] Fair at 12x P/FCF vs sector 14x",
                risks="[MOCK] Cyclical demand | FX drag | Regulatory headwinds",
            )
        if schema is not None and hasattr(schema, "model_fields"):
            from app.models import Assessment, Rebuttal, Thesis, Verdict

            if schema is Assessment:
                return SimpleNamespace(
                    diagnosis=f"[MOCK diagnosis based on: {preview}...]",
                    outlook="[MOCK] Outlook: NEUTRAL, awaiting data.",
                    key_drivers=["mock driver 1", "mock driver 2", "mock driver 3"],
                    news_interpretation="[MOCK] No material news in scope.",
                    reasoning_trace="[MOCK] Reasoning trace: placeholder for testing.",
                    signal_direction="NEUTRAL",
                    signal_strength=0.5,
                )
            if schema in (Thesis,):
                from app.models import Direction, Domain

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
            if schema in (Rebuttal,):
                from app.models import Direction, Domain

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
            if schema is Verdict:
                from app.models import Consensus, Domain

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
        return SimpleNamespace(
            diagnosis=f"[MOCK diagnosis based on: {preview}...]",
            outlook="[MOCK] Outlook: NEUTRAL, awaiting data.",
            key_drivers=["mock driver 1", "mock driver 2", "mock driver 3"],
            news_interpretation="[MOCK] No material news in scope.",
            reasoning_trace="[MOCK] Reasoning trace: this is placeholder text for testing.",
            signal_direction="NEUTRAL",
            signal_strength=0.5,
        )

    def with_structured_output(self, schema):
        return MockModel(schema=schema)

    def bind_tools(self, tools):
        return self


class MockProvider(LLMProvider):
    def provider_name(self) -> str:
        return "mock"

    def get_model(self) -> MockModel:
        return MockModel()


class ProviderRegistry:
    _providers: dict[str, LLMProvider] = {}
    _known_factories: dict[str, type[LLMProvider]] = {
        "minimax": MiniMaxProvider,
        "mock": MockProvider,
    }

    @classmethod
    def register(cls, name: str, provider: LLMProvider) -> None:
        cls._providers[name] = provider
        log.info("provider.registered", name=name, provider=provider.provider_name())

    @classmethod
    def get(cls, name: str) -> LLMProvider:
        if name not in cls._providers:
            factory = cls._known_factories.get(name)
            if factory is None:
                raise ValueError(
                    f"Unknown provider: {name}. Available: {sorted(cls._known_factories)}"
                )
            cls.register(name, factory())
        return cls._providers[name]

    @classmethod
    def list_providers(cls) -> list[str]:
        return sorted(cls._providers or cls._known_factories)

    @classmethod
    def initialize_defaults(cls) -> None:
        for name, factory in cls._known_factories.items():
            if name not in cls._providers:
                cls.register(name, factory())
