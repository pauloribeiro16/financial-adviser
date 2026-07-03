from __future__ import annotations

import beaupy
import pytest

import app.cli_menu as cli_menu
from app.agents import (
    _PERSONA_COMPANY_SECTORS,
    _PERSONA_DOMAINS,
    ALL_AGENTS,
    personas_for_domain,
)
from app.cli_menu import interactive_pick

CENTRAL_BANKERS = {"greenspan", "bernanke", "volcker"}
INVESTORS = {
    "buffett", "lynch", "dalio", "burry", "eisman",
    "grantham", "simons", "taleb", "wood", "thaler", "gundlach",
}


def test_three_central_bankers_macro_only() -> None:
    for pid in CENTRAL_BANKERS:
        assert _PERSONA_DOMAINS[pid] == {"macro"}, pid


def test_dimon_company_only() -> None:
    assert _PERSONA_DOMAINS["dimon"] == {"company"}
    assert "dimon" not in personas_for_domain("macro")


def test_investors_company_and_macro() -> None:
    for pid in INVESTORS:
        assert _PERSONA_DOMAINS[pid] == {"company", "macro"}, pid


def test_company_technology_excludes_dimon_and_central_bankers() -> None:
    result = personas_for_domain("company", "Technology")
    assert len(result) == 11
    assert "dimon" not in result
    for pid in CENTRAL_BANKERS:
        assert pid not in result, pid


def test_company_financial_includes_dimon_excludes_central_bankers() -> None:
    result = personas_for_domain("company", "Financial Services")
    assert len(result) == 12
    assert "dimon" in result
    for pid in CENTRAL_BANKERS:
        assert pid not in result, pid


def test_macro_includes_central_bankers_excludes_dimon() -> None:
    result = personas_for_domain("macro")
    assert len(result) == 14
    for pid in CENTRAL_BANKERS:
        assert pid in result, pid
    assert "dimon" not in result


def test_dimon_sector_restriction_registered() -> None:
    assert _PERSONA_COMPANY_SECTORS["dimon"] == {"Financial Services"}


def test_backward_compat_all_15_still_loadable() -> None:
    assert len(ALL_AGENTS) == 15


def _patch_beaupy(
    monkeypatch: pytest.MonkeyPatch,
    persona_return: list[int],
    company_sector_idx: int = 0,
    ticker_idx: int = 0,
    indicator_return: list[int] | None = None,
    mode_idx: int = 0,
    domain_idx: int | None = None,
) -> None:
    """Patch beaupy.select / select_multiple to deterministic returns.

    Order of beaupy.select calls in interactive_pick (S14-P3):
      1. mode (analyze/watch)
      2. domain
      3. (company) sector  |  (macro) provider
      4. (company) ticker  |  (macro) provider
      5. provider          |  (macro) persona
      6. persona (select_multiple)

    ``mode_idx`` defaults to 0 (analyze). ``domain_idx`` defaults to the
    cursor_index supplied by ``interactive_pick`` (company=0 / macro=1).
    """
    select_calls: list = []
    select_multiple_calls: list = []

    def fake_select(options, **kwargs):
        select_calls.append(options)
        idx = len(select_calls) - 1
        if idx == 0:
            return mode_idx
        if idx == 1:
            return domain_idx if domain_idx is not None else kwargs.get("cursor_index", 0)
        if idx == 2:
            return company_sector_idx
        if idx == 3:
            return ticker_idx
        return kwargs.get("cursor_index", 0)

    def fake_select_multiple(options, **kwargs):
        select_multiple_calls.append(options)
        if options and "—" in options[0]:
            return indicator_return or [0, 1]
        return persona_return

    def fake_confirm(*args, **kwargs):
        return True

    monkeypatch.setattr(beaupy, "select", fake_select)
    monkeypatch.setattr(beaupy, "select_multiple", fake_select_multiple)
    monkeypatch.setattr(beaupy, "confirm", fake_confirm)
    monkeypatch.setattr(cli_menu, "_is_tty", lambda: True)


def test_cli_company_uses_filtered_personas(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_beaupy(
        monkeypatch,
        persona_return=[0],
        company_sector_idx=1,
        ticker_idx=0,
        mode_idx=0,
        domain_idx=0,
    )

    defaults = {
        "domain": "company",
        "target": "AAPL",
        "indicators": [],
        "provider": "mock",
        "analysts": [],
        "rounds": 1,
        "format": "md",
        "include_synthesis": False,
    }

    cfg = interactive_pick(defaults)

    assert cfg["domain"] == "company"
    allowed = personas_for_domain("company", "Technology")
    for pid in cfg["analysts"]:
        assert pid in allowed, f"{pid} not allowed for company/Technology"
    assert "dimon" not in cfg["analysts"]
    for pid in CENTRAL_BANKERS:
        assert pid not in cfg["analysts"], pid


def test_cli_macro_uses_filtered_personas(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_beaupy(
        monkeypatch,
        persona_return=[0],
        indicator_return=[0],
        mode_idx=0,
        domain_idx=1,
    )

    defaults = {
        "domain": "macro",
        "target": "US.FFR",
        "indicators": ["US.FFR"],
        "provider": "mock",
        "analysts": [],
        "rounds": 1,
        "format": "md",
        "include_synthesis": False,
    }

    cfg = interactive_pick(defaults)

    assert cfg["domain"] == "macro"
    allowed = personas_for_domain("macro")
    for pid in cfg["analysts"]:
        assert pid in allowed, f"{pid} not allowed for macro"
    assert "dimon" not in cfg["analysts"]
    assert any(pid in cfg["analysts"] for pid in CENTRAL_BANKERS)


def test_cli_company_financial_services_can_pick_dimon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_beaupy(
        monkeypatch,
        persona_return=[0],
        company_sector_idx=0,
        ticker_idx=0,
    )

    available = personas_for_domain("company", "Financial Services")
    dimon_local_idx = available.index("dimon")

    _patch_beaupy(
        monkeypatch,
        persona_return=[dimon_local_idx],
        company_sector_idx=0,
        ticker_idx=0,
    )

    defaults = {
        "domain": "company",
        "target": "JPM",
        "indicators": [],
        "provider": "mock",
        "analysts": [],
        "rounds": 1,
        "format": "md",
        "include_synthesis": False,
    }

    cfg = interactive_pick(defaults)
    assert "dimon" in cfg["analysts"]
