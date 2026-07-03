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

    def invoke(self, messages, config=None):
        user_content = messages[-1]["content"] if messages else ""
        preview = user_content[:60].replace("\n", " ")
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
        return self

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
