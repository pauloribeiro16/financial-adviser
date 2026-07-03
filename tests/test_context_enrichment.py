from __future__ import annotations

from app.pipeline.context import build_company_context, render_context_markdown

REPO_ROOT = "/Users/pauloribeiro/Desktop/Projetos/financial-adviser"
MSFT_TICKER = "MSFT"


def test_rendered_company_context_contains_fundamentals() -> None:
    """build_company_context('MSFT') must produce a context whose rendered
    Markdown surfaces the yfinance fundamentals (income stmt / balance sheet /
    cashflow) instead of silently dropping them."""
    ctx = build_company_context(MSFT_TICKER)
    md = render_context_markdown(ctx, "company")
    assert "## Income statement (yfinance" in md, (
        f"missing income statement section in render:\n{md[:2000]}"
    )
    assert "## Cash flow (yfinance" in md, (
        "missing cashflow section in render"
    )
    assert "Free Cash Flow" in md, "Free Cash Flow line not rendered"
    assert "Capital Expenditure" in md, "Capital Expenditure line not rendered"
    fundamentals = ctx.get("fundamentals") or {}
    assert fundamentals.get("income_stmt"), "fundamentals.income_stmt empty"
    assert fundamentals.get("balance_sheet"), "fundamentals.balance_sheet empty"
    assert fundamentals.get("cashflow"), "fundamentals.cashflow empty"


def test_rendered_context_contains_macro_indicators() -> None:
    """Company evaluations must surface the VIX / UST10Y / Credit Spread macro
    context so macro-aware personas (Gundlach, Simons, Dalio) have something
    concrete to reference."""
    ctx = build_company_context(MSFT_TICKER)
    md = render_context_markdown(ctx, "company")
    assert "## Macro context" in md, "missing macro context section in render"
    macro_block = md.split("## Macro context", 1)[1]
    hits = sum(
        1 for needle in ("VIX", "10Y Treasury", "Credit Spread")
        if needle in macro_block
    )
    assert hits >= 2, (
        f"expected >=2 of (VIX, 10Y Treasury, Credit Spread) in macro block; "
        f"got {hits}\n--- block ---\n{macro_block[:1000]}"
    )
    macro_ctx = ctx.get("macro") or {}
    indicators = macro_ctx.get("indicators") or []
    assert len(indicators) == 3, f"expected 3 macro indicators, got {len(indicators)}"
    series_ids = {i.get("series_id") for i in indicators}
    assert {"VIXCLS", "DGS10", "BAMLH0A0HYM2"} <= series_ids, (
        f"missing series ids in {series_ids}"
    )


def test_stale_xbrl_tags_filtered() -> None:
    """_summarize_facts must drop tags whose latest_period_end is >5y old.

    Concretely: MSFT still publishes a ``Revenues`` XBRL tag with
    latest_period_end=2010-12-31 (a discontinued tag). It must NOT appear in
    the rendered context or in ctx['edgar']['facts'], while the current
    ``RevenueFromContractWithCustomerExcludingAssessedTax`` (2026-03-31) must.
    """
    ctx = build_company_context(MSFT_TICKER)
    facts = (ctx.get("edgar") or {}).get("facts") or {}
    assert "Revenues" not in facts, (
        f"stale 'Revenues' tag still present in facts: {list(facts.keys())}"
    )
    assert "RevenueFromContractWithCustomerExcludingAssessedTax" in facts, (
        "current revenue tag is missing — stale filter may be too aggressive"
    )
    for k, v in facts.items():
        end = v.get("latest_period_end") or ""
        assert end >= "2021-01-01", (
            f"tag {k} has suspect latest_period_end={end} (<2021 cutoff)"
        )

    md = render_context_markdown(ctx, "company")
    assert "- **Revenues**" not in md, "stale 'Revenues' tag still rendered"
    assert "RevenueFromContractWithCustomerExcludingAssessedTax" in md, (
        "current revenue tag not rendered"
    )
