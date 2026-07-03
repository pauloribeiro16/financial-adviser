from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.debate.engine import build_rebuttal_messages, build_thesis_messages
from app.models import Direction, Domain, Thesis


@pytest.fixture
def one_prior_thesis() -> Thesis:
    return Thesis(
        agent_id="buffett",
        target="MSFT",
        domain=Domain.COMPANY,
        round=0,
        verdict=Direction.BULLISH,
        conviction=0.7,
        key_drivers=["moat"],
        reasoning="prior reasoning",
        data_used=["ctx"],
    )


def test_analysis_pillars_file_exists_and_loads():
    p = Path("app/prompts/_shared/analysis_pillars.md")
    assert p.exists(), "pillars file missing"
    txt = p.read_text(encoding="utf-8")
    for kw in ("Business Lifecycle", "Moat", "Growth Engines",
               "Financial Health", "Bear Case", "Valuation"):
        assert kw in txt, f"missing pillar section: {kw}"
    print("OK; 6 pillars present")


def test_thesis_user_prompt_requires_6_pillars():
    msgs = build_thesis_messages("buffett", "MSFT", "company", date.today(), "x")
    u = msgs[1]["content"].lower()
    for kw in ("business lifecycle", "moat", "growth engines",
               "financial health", "bear case", "valuation"):
        assert kw in u, f"missing {kw}"
    fields = set(Thesis.model_fields.keys())
    assert fields == {
        "agent_id", "target", "domain", "round", "verdict",
        "conviction", "key_drivers", "reasoning", "data_used",
    }, fields
    print("OK; 6 pillars enforced, schema unchanged")


def test_thesis_system_prompt_includes_pillars():
    msgs = build_thesis_messages("buffett", "MSFT", "company", date.today(), "x")
    s = msgs[0]["content"]
    for kw in ("Business Lifecycle", "Moat Analysis",
               "Growth Engines", "Financial Health",
               "Bear Case", "Valuation Dashboard"):
        assert kw in s, f"system prompt missing {kw}"
    print("OK; system prompt contains pillars")


def test_rebuttal_user_prompt_demands_pillar_challenges(one_prior_thesis):
    msgs = build_rebuttal_messages(
        "taleb", "MSFT", "company", date.today(), "x", [one_prior_thesis]
    )
    u = msgs[1]["content"].lower()
    for kw in ("pillar", "weakest", "data point", "citation"):
        assert kw in u, f"missing {kw}"
    print("OK; rebuttal demands pillar challenges")


def test_prompts_still_dont_ask_for_text_input(one_prior_thesis):
    msgs_t = build_thesis_messages("buffett", "MSFT", "company", date.today(), "x")
    msgs_r = build_rebuttal_messages(
        "taleb", "MSFT", "company", date.today(), "x", [one_prior_thesis]
    )
    for m in [msgs_t, msgs_r]:
        for role, content in m:
            assert "comma-separated" not in content.lower(), (
                f"text input regression in {role}"
            )
    print("OK; no text input regression")


def test_pillars_loaded_for_every_persona():
    personas = [
        "buffett", "lynch", "dalio", "burry", "greenspan",
        "bernanke", "volcker", "dimon", "eisman", "grantham",
        "simons", "taleb", "wood", "gundlach", "thaler",
    ]
    for pid in personas:
        msgs = build_thesis_messages(pid, "AAPL", "company", date.today(), "ctx")
        s = msgs[0]["content"]
        assert "Valuation Dashboard" in s, f"{pid} missing pillars"
    print(f"OK; pillars loaded for all {len(personas)} personas")
