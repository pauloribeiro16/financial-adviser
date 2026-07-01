from __future__ import annotations

from typing import Any

from app.catalog import get_catalog
from app.logging import get_logger
from app.pipeline import edgar, macro, market

log = get_logger(__name__)


def build_company_context(ticker: str) -> dict[str, Any]:
    ticker = ticker.upper().strip()
    log.info("pipeline.context.build_company", ticker=ticker)

    edgar_packet = edgar.fetch_packet(ticker)
    quote = market.quote(ticker)
    fundamentals = market.fundamentals(ticker)

    return {
        "ticker": ticker,
        "edgar": edgar_packet,
        "quote": quote,
        "fundamentals": fundamentals,
    }


def build_macro_context(indicator_ids: list[str] | None = None, as_of: str | None = None) -> dict[str, Any]:
    log.info("pipeline.context.build_macro", indicators=indicator_ids, as_of=as_of)
    catalog = get_catalog()
    if indicator_ids:
        wanted = set(indicator_ids)
        catalog = [i for i in catalog if i.indicator_id in wanted]
    series = []
    for ind in catalog:
        if not ind.source_series:
            continue
        obs = macro.fetch_observation(ind.source_series, as_of=as_of)
        series.append({
            "indicator_id": ind.indicator_id,
            "name": ind.name,
            "category": ind.category.value,
            "frequency": ind.frequency.value,
            "units": ind.units,
            "transformation": ind.transformation.value,
            **obs,
        })
    return {"series": series, "as_of": as_of}


def render_context_markdown(ctx: dict[str, Any], kind: str) -> str:
    if kind == "company":
        return _render_company(ctx)
    if kind == "macro":
        return _render_macro(ctx)
    return ""


def _render_company(ctx: dict[str, Any]) -> str:
    ticker = ctx.get("ticker", "")
    edgar = ctx.get("edgar") or {}
    quote = ctx.get("quote") or {}
    sections: list[str] = [f"# Data context: {ticker}"]

    sub = edgar.get("submissions") or {}
    if sub:
        sections.append("\n## Company profile (SEC EDGAR)")
        sections.append(f"- Name: {sub.get('name')}")
        sections.append(f"- SIC: {sub.get('sic')} ({sub.get('sicDescription')})")
        sections.append(f"- Exchanges: {sub.get('exchanges')}")
        sections.append(f"- State of incorporation: {sub.get('stateOfIncorporation')}")
        sections.append(f"- Fiscal year end: {sub.get('fiscalYearEnd')}")

    latest_10k = edgar.get("latest_10k")
    if latest_10k:
        sections.append("\n## Latest 10-K filing")
        sections.append(f"- Form: {latest_10k.get('form')}")
        sections.append(f"- Filed: {latest_10k.get('filing_date')}")
        sections.append(f"- Accession: {latest_10k.get('accession')}")

    facts = edgar.get("facts") or {}
    if facts:
        sections.append("\n## Structured financials (XBRL companyfacts, latest)")
        for k, v in facts.items():
            sections.append(f"- **{k}** ({v.get('unit')}): {v.get('latest_value')} — period ending {v.get('latest_period_end')} (form {v.get('latest_form')})")

    if quote:
        sections.append("\n## Market quote (yfinance)")
        for k in ["price", "previous_close", "market_cap", "currency",
                  "trailing_pe", "forward_pe", "price_to_book", "dividend_yield",
                  "beta", "52w_high", "52w_low", "sector", "industry"]:
            v = quote.get(k)
            if v is not None:
                sections.append(f"- {k}: {v}")

    return "\n".join(sections) + "\n"


def _render_macro(ctx: dict[str, Any]) -> str:
    series = ctx.get("series", [])
    if not series:
        return "# Data context: macro\n\n_(no series)_\n"
    out = ["# Data context: macro", "", f"as_of: {ctx.get('as_of') or 'latest'}", ""]
    for s in series:
        out.append(f"## {s['indicator_id']} — {s.get('name')} ({s.get('category')})")
        out.append(f"- latest: **{s.get('latest_value')}** on {s.get('latest_date')}")
        out.append(f"- units: {s.get('units')} ({s.get('transformation')}) frequency: {s.get('frequency')}")
        obs = s.get("observations", []) or []
        if obs:
            tail = ", ".join(f"{o['date']}={o['value']}" for o in reversed(obs[-6:]))
            out.append(f"- last 6: {tail}")
        out.append("")
    return "\n".join(out)
