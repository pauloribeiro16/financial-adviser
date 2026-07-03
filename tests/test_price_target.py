from __future__ import annotations

import pytest

from app.watch.price_target import compute_buy_price, moat_strength_from_text


def test_positive_signal_company_fcf_above_sector_raises_buy_price() -> None:
    buy = compute_buy_price(
        current_price=100.0,
        sector_target_fcf_yield=0.05,
        company_fcf_yield=0.08,
        moat_strength=4,
    )
    assert buy > 100.0


def test_negative_signal_company_fcf_below_sector_lowers_buy_price() -> None:
    buy = compute_buy_price(
        current_price=100.0,
        sector_target_fcf_yield=0.08,
        company_fcf_yield=0.04,
        moat_strength=3,
    )
    assert buy < 100.0


def test_moat_scales_buy_price_higher_with_stronger_moat() -> None:
    low = compute_buy_price(
        current_price=100.0,
        sector_target_fcf_yield=0.05,
        company_fcf_yield=0.05,
        moat_strength=1,
    )
    high = compute_buy_price(
        current_price=100.0,
        sector_target_fcf_yield=0.05,
        company_fcf_yield=0.05,
        moat_strength=5,
    )
    assert high > low


def test_moat_margin_range() -> None:
    low = compute_buy_price(100.0, 0.05, 0.05, 1)
    high = compute_buy_price(100.0, 0.05, 0.05, 5)
    assert low == pytest.approx(100.0 * 0.79, rel=1e-6)
    assert high == pytest.approx(100.0 * 0.91, rel=1e-6)


def test_edge_company_fcf_zero_returns_positive_value() -> None:
    buy = compute_buy_price(100.0, 0.05, 0.0, 3)
    assert buy > 0


def test_edge_company_fcf_negative_returns_current_times_1_5() -> None:
    buy = compute_buy_price(100.0, 0.05, -0.02, 3)
    assert buy == pytest.approx(150.0, rel=1e-6)


def test_edge_sector_target_zero_returns_current_times_0_7() -> None:
    buy = compute_buy_price(100.0, 0.0, 0.05, 3)
    assert buy == pytest.approx(70.0, rel=1e-6)


def test_edge_sector_target_negative_falls_through_to_cheapish() -> None:
    buy = compute_buy_price(100.0, -0.01, 0.05, 3)
    assert buy == pytest.approx(70.0, rel=1e-6)


def test_moat_strength_above_5_is_clamped() -> None:
    a = compute_buy_price(100.0, 0.05, 0.05, 5)
    b = compute_buy_price(100.0, 0.05, 0.05, 10)
    assert a == b


def test_moat_strength_below_1_is_clamped() -> None:
    a = compute_buy_price(100.0, 0.05, 0.05, 1)
    b = compute_buy_price(100.0, 0.05, 0.05, -3)
    assert a == b


def test_moat_strength_from_text_three_green_dots_returns_5() -> None:
    assert moat_strength_from_text("🟢🟢🟢 moat widening") == 5


def test_moat_strength_from_text_two_green_returns_4() -> None:
    assert moat_strength_from_text("🟢🟢 stable moat") == 4


def test_moat_strength_from_text_yellow_returns_3() -> None:
    assert moat_strength_from_text("🟡 moderate moat") == 3


def test_moat_strength_from_text_red_returns_2() -> None:
    assert moat_strength_from_text("🔴 eroding moat") == 2


def test_moat_strength_from_text_absent_returns_1() -> None:
    assert moat_strength_from_text("") == 1
    assert moat_strength_from_text("no moat, commodity") == 1


def test_moat_strength_from_text_widening_keyword_returns_5() -> None:
    assert moat_strength_from_text("Competitive advantage is widening.") == 5


def test_moat_strength_from_text_eroding_keyword_returns_2() -> None:
    assert moat_strength_from_text("Moat is eroding rapidly.") == 2


def test_moat_strength_from_text_unknown_defaults_to_3() -> None:
    assert moat_strength_from_text("Some neutral commentary here.") == 3
