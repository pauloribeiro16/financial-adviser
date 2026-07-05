from __future__ import annotations

from pathlib import Path

from app.sectors import load_sector
from app.watch.aggregator import WatchSummary
from app.watch.markdown_renderer import (
    GREEN,
    NA,
    RED,
    YELLOW,
    indicator_rows_for_ticker,
    rate_indicator,
    render_company_current_md,
    render_sector_index,
)
from app.watch.reference_reader import DebateRef


def _find_spec(specs, spec_id: str):
    matches = [s for s in specs if s.id == spec_id]
    assert matches, f"spec {spec_id} not found"
    return matches[0]


def test_rate_indicator_higher_is_better() -> None:
    specs = load_sector("energy")
    fcf = _find_spec(specs, "fcf_yield")
    assert fcf.healthier_is == "higher"

    assert rate_indicator(fcf, fcf.healthy_threshold + 0.01) == GREEN
    assert rate_indicator(fcf, fcf.healthy_threshold) == GREEN
    assert rate_indicator(fcf, (fcf.healthy_threshold + fcf.warning_threshold) / 2) == YELLOW
    assert rate_indicator(fcf, fcf.warning_threshold) == YELLOW
    assert rate_indicator(fcf, fcf.warning_threshold - 0.01) == RED
    assert rate_indicator(fcf, None) == NA


def test_rate_indicator_lower_is_better() -> None:
    specs = load_sector("energy")
    nde = _find_spec(specs, "net_debt_ebitda")
    assert nde.healthier_is == "lower"

    assert rate_indicator(nde, nde.healthy_threshold - 0.1) == GREEN
    assert rate_indicator(nde, nde.healthy_threshold) == GREEN
    assert rate_indicator(nde, (nde.healthy_threshold + nde.warning_threshold) / 2) == YELLOW
    assert rate_indicator(nde, nde.warning_threshold) == YELLOW
    assert rate_indicator(nde, nde.warning_threshold + 0.1) == RED
    assert rate_indicator(nde, None) == NA


def test_rate_indicator_mid_is_green_within_tolerance() -> None:
    specs = load_sector("energy")
    div = _find_spec(specs, "dividend_yield")
    assert div.healthier_is == "mid"

    assert rate_indicator(div, div.healthy_threshold) == GREEN
    assert rate_indicator(div, div.healthy_threshold * 1.10) == GREEN
    assert rate_indicator(div, div.healthy_threshold * 0.90) == GREEN
    assert rate_indicator(div, div.healthy_threshold * 5) == RED
    assert rate_indicator(div, div.healthy_threshold * 0.01) == RED
    assert rate_indicator(div, None) == NA


def test_render_company_current_md_has_all_sections(tmp_path: Path) -> None:
    ticker_dir = tmp_path / "Energy" / "XOM"
    ticker_dir.mkdir(parents=True)
    debate = ticker_dir / "2026-07-03T12-00-00_000_mock_debate.md"
    debate.write_text("# debate", encoding="utf-8")
    ref = DebateRef(
        ticker="XOM",
        sector="Energy",
        debate_path=debate,
        meta_path=None,
        meta={"provider": "mock"},
        debate_mtime=debate.stat().st_mtime,
    )
    summary = WatchSummary(
        moat="\U0001f7e2\U0001f7e2\U0001f7e2 deep moat widening",
        cycle_phase="Capital Return",
        financial_health="FCF margin 12%, net debt 1.0x",
        valuation="Fair at 12x P/FCF",
        risks="Cyclical demand | Regulatory",
        providers_used="mock",
    )
    rows = indicator_rows_for_ticker("XOM", load_sector("energy"))

    md = render_company_current_md(
        summary=summary,
        ticker="XOM",
        sector="Energy",
        debate_ref=ref,
        indicator_rows=rows,
        buy_price=92.0,
        sector_target_fcf_yield=0.06,
        current_price=114.0,
        indicator_specs=load_sector("energy"),
        moat_strength=5,
    )

    assert "# XOM" in md
    assert "## Summary (5 bullets)" in md
    assert "**Moat:**" in md
    assert "**Cycle:**" in md
    assert "**Financial Health:**" in md
    assert "**Valuation:**" in md
    assert "**Risks:**" in md
    assert "## Sector indicators" in md
    assert "## Buy target" in md
    assert "**Buy at:** $92" in md
    assert "**Current price:** $114" in md
    assert "Distance to buy" in md
    assert "## Trail of debates" in md


def test_render_company_current_md_handles_no_indicator_rows(tmp_path: Path) -> None:
    ticker_dir = tmp_path / "Energy" / "XOM"
    ticker_dir.mkdir(parents=True)
    debate = ticker_dir / "2026-07-03T12-00-00_000_mock_debate.md"
    debate.write_text("# debate", encoding="utf-8")
    ref = DebateRef(
        ticker="XOM",
        sector="Energy",
        debate_path=debate,
        meta_path=None,
        meta={"provider": "mock"},
        debate_mtime=debate.stat().st_mtime,
    )
    summary = WatchSummary(
        moat="🟡 moat",
        cycle_phase="Capital Return",
        financial_health="health",
        valuation="valuation",
        risks="risks",
        providers_used="mock",
    )
    md = render_company_current_md(
        summary=summary,
        ticker="XOM",
        sector="Energy",
        debate_ref=ref,
        indicator_rows=[],
        buy_price=92.0,
        sector_target_fcf_yield=0.06,
        current_price=0.0,
        moat_strength=3,
    )
    assert "_(none)_" in md or "n/a" in md
    assert "**Current price:**" in md


def test_render_sector_index_includes_all_columns() -> None:
    entries = [
        {"ticker": "XOM", "name": "ExxonMobil", "verdict": "BULLISH",
         "buy_price": 92.0, "conviction": 0.65, "last_updated": "2026-07-03"},
        {"ticker": "CVX", "name": "Chevron", "verdict": "NEUTRAL",
         "buy_price": 145.0, "conviction": 0.50, "last_updated": "2026-07-03"},
    ]
    md = render_sector_index("Energy", entries)
    assert "| Ticker | Name | Verdict | Buy @ | Conviction | Last |" in md
    assert "XOM" in md
    assert "ExxonMobil" in md
    assert "$92.00" in md
    assert "0.65" in md
    assert "Chevron" in md
    assert "$145.00" in md


def test_render_sector_index_empty_entries() -> None:
    md = render_sector_index("Energy", [])
    assert "(no tickers)" in md


def test_indicator_rows_for_ticker_returns_all_specs() -> None:
    rows = indicator_rows_for_ticker("XOM", load_sector("energy"))
    assert len(rows) == len(load_sector("energy"))
    for name, value, rating, threshold in rows:
        assert isinstance(name, str)
        assert isinstance(value, str)
        assert rating in {GREEN, YELLOW, RED, NA}
        assert isinstance(threshold, str)


def test_indicator_rows_for_ticker_handles_unknown_ticker() -> None:
    rows = indicator_rows_for_ticker("ZZZZZZ", load_sector("energy"))
    assert len(rows) == len(load_sector("energy"))
    for _, value, rating, _ in rows:
        assert rating == NA or rating in {GREEN, YELLOW, RED}
        assert value == "n/a" or value.endswith("%") or value.endswith("x") or "e" in value


def test_indicator_rows_extracts_from_cache(tmp_path: Path) -> None:
    from app.pipeline import cache as pipeline_cache

    pipeline_cache.CACHE_DIR = tmp_path / "cache"
    pipeline_cache.CACHE_DIR.mkdir(parents=True)

    fundamentals = {
        "income_stmt": [
            {
                "period": "2025-12-31",
                "Total Revenue": 100_000_000_000.0,
                "Gross Profit": 50_000_000_000.0,
                "EBITDA": 25_000_000_000.0,
                "EBIT": 20_000_000_000.0,
            },
            {
                "period": "2024-12-31",
                "Total Revenue": 90_000_000_000.0,
                "EBIT": 17_000_000_000.0,
            },
        ],
        "balance_sheet": [
            {
                "period": "2025-12-31",
                "Net Debt": 30_000_000_000.0,
                "Ordinary Shares Number": 1_000_000_000.0,
            },
            {
                "period": "2024-12-31",
                "Ordinary Shares Number": 1_050_000_000.0,
            },
        ],
        "cashflow": [
            {
                "period": "2025-12-31",
                "Free Cash Flow": 6_000_000_000.0,
                "Capital Expenditure": -10_000_000_000.0,
            },
        ],
    }
    market = {
        "market_cap": 100_000_000_000.0,
        "price": 100.0,
        "dividend_yield": 0.04,
    }
    pipeline_cache.put("fundamentals", "FAKE", fundamentals)
    pipeline_cache.put("market", "FAKE", market)

    rows = indicator_rows_for_ticker("FAKE", load_sector("energy"))
    by_name = {r[0]: r for r in rows}
    fcf_row = by_name.get("FCF Yield")
    assert fcf_row is not None
    assert fcf_row[1] == "6.0%"
    assert fcf_row[2] == GREEN
    rev_row = next((r for r in rows if "Revenue" in r[0] or "Margin" in r[0]), None)
    assert rev_row is not None


def test_rate_indicator_handles_malformed_values() -> None:
    specs = load_sector("energy")
    fcf = _find_spec(specs, "fcf_yield")
    nde = _find_spec(specs, "net_debt_ebitda")

    assert rate_indicator(fcf, -1e9) == RED
    assert rate_indicator(fcf, 1e9) == GREEN
    assert rate_indicator(nde, -1e9) == GREEN
    assert rate_indicator(nde, 1e9) == RED
    assert rate_indicator(fcf, float("nan")) == NA
    assert rate_indicator(fcf, float("inf")) == GREEN
    assert rate_indicator(fcf, 0.0) == RED
    assert rate_indicator(fcf, 0.04) == YELLOW
