from __future__ import annotations

import pytest

import app.cli_menu as cli_menu
from app.cli_menu import (
    POPULAR_TICKERS,
    SECTOR_TICKERS,
    _safe,
    interactive_pick,
)

EXPECTED_SECTORS = ["Financial Services", "Technology", "Healthcare", "Energy"]


def test_sector_tickers_covers_all_four_sectors() -> None:
    assert set(SECTOR_TICKERS.keys()) == set(EXPECTED_SECTORS)


def test_sector_tickers_has_6_to_8_per_sector() -> None:
    for sector, tickers in SECTOR_TICKERS.items():
        assert 6 <= len(tickers) <= 8, f"{sector} has {len(tickers)} tickers"


def test_popular_tickers_flat_derived_consistently() -> None:
    expected = [t for sector in SECTOR_TICKERS.values() for t in sector]
    assert POPULAR_TICKERS == expected
    expected_count = sum(len(v) for v in SECTOR_TICKERS.values())
    assert len(POPULAR_TICKERS) == expected_count


def test_tickers_unique_within_each_sector() -> None:
    for sector, tickers in SECTOR_TICKERS.items():
        symbols = [sym for sym, _ in tickers]
        assert len(symbols) == len(set(symbols)), f"duplicates in {sector}: {symbols}"


def test_ticker_can_be_resolved_to_sector() -> None:
    for sym, _ in POPULAR_TICKERS:
        matches = [
            sec for sec, tickers in SECTOR_TICKERS.items()
            if any(t == sym for t, _ in tickers)
        ]
        assert len(matches) == 1, f"{sym} resolved to {matches}"


def test_safe_returns_fallback_when_prompt_raises() -> None:
    def boom() -> int:
        raise RuntimeError("simulated beaupy failure")

    result = _safe(boom, fallback=42, propagate_cancel=False)
    assert result == 42


def test_safe_propagates_keyboard_interrupt() -> None:
    def cancel() -> int:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        _safe(cancel, fallback=42)


def test_interactive_pick_company_falls_back_on_beaupy_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import beaupy

    calls: list[str] = []

    def fake_select(options, **kwargs):  # noqa: ANN001, ANN201
        calls.append("select")
        raise RuntimeError("forced beaupy failure")

    def fake_select_multiple(options, **kwargs):  # noqa: ANN001, ANN201
        calls.append("select_multiple")
        raise RuntimeError("forced beaupy failure")

    def fake_confirm(*args: object, **kwargs: object) -> bool:
        calls.append("confirm")
        return True

    monkeypatch.setattr(beaupy, "select", fake_select)
    monkeypatch.setattr(beaupy, "select_multiple", fake_select_multiple)
    monkeypatch.setattr(beaupy, "confirm", fake_confirm)
    monkeypatch.setattr(cli_menu, "_is_tty", lambda: True)

    defaults = {
        "domain": "company",
        "target": "AAPL",
        "indicators": [],
        "provider": "mock",
        "analysts": ["buffett"],
        "rounds": 2,
        "format": "md",
        "include_synthesis": False,
    }

    cfg = interactive_pick(defaults)

    assert cfg["domain"] == "company"
    assert cfg["target"] == "AAPL"
    assert cfg["indicators"] == []
    assert cfg["provider"] == "mock"
    assert "buffett" in cfg["analysts"]
    assert cfg["rounds"] == 2
    assert "select" in calls and "confirm" in calls
    assert calls.count("select") >= 3
