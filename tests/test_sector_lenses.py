from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest

from app.agents import PROMPTS_DIR
from app.debate.engine import (
    _run_round_theses,
    _sector_lens_text,
    build_rebuttal_messages,
    build_thesis_messages,
    run_debate,
)
from app.models import Direction, Domain, Rebuttal, Thesis
from app.providers import LLMProvider, ProviderRegistry

SECTOR_LENS_DIR = PROMPTS_DIR / "_shared" / "sector_lenses"
KNOWN_SECTORS = {
    "Financial Services": "financial",
    "Technology": "technology",
    "Healthcare": "healthcare",
    "Energy": "energy",
}


def test_lens_files_exist() -> None:
    for slug in ("financial", "technology", "healthcare", "energy"):
        assert (SECTOR_LENS_DIR / f"{slug}.md").exists(), f"missing lens file: {slug}.md"


@pytest.mark.parametrize(
    "slug",
    ["financial", "technology", "healthcare", "energy"],
)
def test_lens_contains_discount_section(slug: str) -> None:
    text = (SECTOR_LENS_DIR / f"{slug}.md").read_text(encoding="utf-8")
    assert "## Metrics to discount" in text


@pytest.mark.parametrize(
    "slug",
    ["financial", "technology", "healthcare", "energy"],
)
def test_lens_contains_matter_section(slug: str) -> None:
    text = (SECTOR_LENS_DIR / f"{slug}.md").read_text(encoding="utf-8")
    assert "## Metrics that matter here" in text


@pytest.mark.parametrize(
    "slug",
    ["financial", "technology", "healthcare", "energy"],
)
def test_lens_contains_moat_section(slug: str) -> None:
    text = (SECTOR_LENS_DIR / f"{slug}.md").read_text(encoding="utf-8")
    assert "## Dominant moat types" in text


@pytest.mark.parametrize(
    "slug",
    ["financial", "technology", "healthcare", "energy"],
)
def test_lens_contains_risk_section(slug: str) -> None:
    text = (SECTOR_LENS_DIR / f"{slug}.md").read_text(encoding="utf-8")
    assert "## Top risks" in text


@pytest.mark.parametrize(
    ("sector", "slug"),
    list(KNOWN_SECTORS.items()),
)
def test_sector_lens_lookup_known(sector: str, slug: str) -> None:
    text = _sector_lens_text(sector)
    expected = (SECTOR_LENS_DIR / f"{slug}.md").read_text(encoding="utf-8")
    assert text == expected
    assert f"Sector Lens: {sector}" in text or slug in text.lower()


@pytest.mark.parametrize("sector", [None, "Industrials", "Real Estate", "Consumer Staples", ""])
def test_sector_lens_lookup_unknown_returns_empty(sector: str | None) -> None:
    assert _sector_lens_text(sector) == ""


def test_thesis_prompt_includes_financial_lens() -> None:
    msgs = build_thesis_messages(
        "buffett",
        "JPM",
        "company",
        date(2025, 3, 31),
        "context md",
        sector="Financial Services",
    )
    system = msgs[0]["content"]
    user = msgs[1]["content"]
    assert "CET1" in system
    assert "## Metrics to discount" in system
    assert "Moat Analysis" in system
    assert "## Metrics to discount" not in user


def test_thesis_prompt_no_lens_when_unknown_sector() -> None:
    msgs = build_thesis_messages(
        "buffett",
        "JPM",
        "company",
        date(2025, 3, 31),
        "context md",
        sector="Real Estate",
    )
    system = msgs[0]["content"]
    user = msgs[1]["content"]
    assert "Moat Analysis" in system
    assert "## Metrics to discount" not in system
    assert "## Metrics to discount" not in user


def test_rebuttal_prompt_includes_lens() -> None:
    prior = [
        Thesis(
            agent_id="taleb",
            target="JPM",
            domain=Domain.COMPANY,
            round=0,
            verdict=Direction.BULLISH,
            conviction=0.6,
            key_drivers=["a"],
            reasoning="x",
            data_used=["y"],
        )
    ]
    msgs = build_rebuttal_messages(
        "buffett",
        "JPM",
        "company",
        date(2025, 3, 31),
        "context md",
        prior,
        sector="Financial Services",
    )
    system = msgs[0]["content"]
    user = msgs[1]["content"]
    assert "CET1" in system
    assert "## Metrics to discount" in system
    assert "Moat Analysis" in system
    assert "## Metrics to discount" not in user


class _CaptureModel:
    captured: list[dict[str, Any]] = []

    def __init__(self, schema: Any = None) -> None:
        self._schema = schema

    def with_structured_output(self, schema: Any) -> _CaptureModel:
        return _CaptureModel(schema)

    def bind_tools(self, tools: Any) -> _CaptureModel:
        return self

    def invoke(self, messages: Any, config: Any = None) -> Any:
        if self._schema is Thesis:
            _CaptureModel.captured.append({"messages": messages, "schema": Thesis})
            return Thesis(
                agent_id="mock",
                target="PFE",
                domain=Domain.COMPANY,
                round=0,
                verdict=Direction.NEUTRAL,
                conviction=0.5,
                key_drivers=["a"],
                reasoning="[mock]",
                data_used=["x"],
            )
        if self._schema is Rebuttal:
            return Rebuttal(
                agent_id="mock",
                target="PFE",
                domain=Domain.COMPANY,
                round=1,
                targets=["other"],
                concessions=["c"],
                disagreements=["d"],
                revised_verdict=Direction.NEUTRAL,
                revised_conviction=0.5,
                reasoning="[mock]",
            )
        from app.models import Verdict
        if self._schema is Verdict:
            from app.models import Consensus
            return Verdict(
                target="PFE",
                domain=Domain.COMPANY,
                consensus=Consensus.NEUTRAL,
                bull_count=0,
                bear_count=0,
                neutral_count=1,
                avg_conviction=0.5,
                points_of_agreement=[],
                points_of_disagreement=[],
                final_call="[mock]",
                confidence=0.5,
                summary="[mock]",
            )
        return SimpleNamespace(text="{}")


class _CaptureProvider(LLMProvider):
    def provider_name(self) -> str:
        return "mock"

    def get_model(self) -> _CaptureModel:
        return _CaptureModel()


def test_run_round_theses_passes_sector_to_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    _CaptureModel.captured = []
    ProviderRegistry.register("mock", _CaptureProvider())
    try:
        provider = ProviderRegistry.get("mock")
        _run_round_theses(
            analysts=["buffett"],
            target="PFE",
            domain="company",
            target_date=date(2025, 3, 31),
            context_md="ctx",
            provider=provider,
            sector="Healthcare",
        )
        assert _CaptureModel.captured, "expected at least one captured thesis call"
        first_msgs = _CaptureModel.captured[0]["messages"]
        system = first_msgs[0]["content"]
        assert "Patent cliff" in system or "FDA" in system
        assert "## Metrics to discount" in system
    finally:
        ProviderRegistry._providers.pop("mock", None)


def test_run_debate_backward_compatible_no_sector() -> None:
    _CaptureModel.captured = []
    ProviderRegistry.register("mock", _CaptureProvider())
    try:
        result = run_debate(
            analysts=["buffett"],
            target="PFE",
            domain="company",
            target_date=date(2025, 3, 31),
            context_md="ctx",
            rounds=1,
            provider_name="mock",
        )
        assert result.theses
        first_msgs = _CaptureModel.captured[0]["messages"]
        system = first_msgs[0]["content"]
        assert "## Metrics to discount" not in system
    finally:
        ProviderRegistry._providers.pop("mock", None)
