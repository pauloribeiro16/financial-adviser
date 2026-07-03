from __future__ import annotations

from typing import Any

from app.catalog import get_catalog
from app.logging import get_logger
from app.pipeline import edgar, macro, market, news
from app.pipeline.metrics import derive_metrics

log = get_logger(__name__)

MACRO_SERIES_FOR_COMPANY: dict[str, str] = {
    "VIX (CBOE Volatility)": "VIXCLS",
    "10Y Treasury Yield": "DGS10",
    "IG-HY Credit Spread (OAS)": "BAMLH0A0HYM2",
}

_INCOME_KEYS = (
    "Total Revenue",
    "Operating Revenue",
    "EBITDA",
    "EBIT",
    "Net Income From Continuing Operation Net Minority Interest",
    "Reconciled Depreciation",
    "Basic EPS",
    "Diluted EPS",
)
_BALANCE_KEYS = (
    "Total Assets",
    "Total Liabilities Net Minority Interest",
    "Stockholders Equity",
    "Common Stock Equity",
    "Cash And Cash Equivalents",
    "Total Debt",
    "Net Debt",
    "Working Capital",
)
_CASHFLOW_KEYS = (
    "Operating Cash Flow",
    "Free Cash Flow",
    "Capital Expenditure",
    "Repurchase Of Capital Stock",
    "Issuance Of Debt",
    "Repayment Of Debt",
    "End Cash Position",
)


def _fmt_billions(v: Any) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    a = abs(f)
    if a >= 1e9:
        return f"${f / 1e9:.2f}B"
    if a >= 1e6:
        return f"${f / 1e6:.1f}M"
    if a >= 1e3:
        return f"${f / 1e3:.1f}K"
    return f"${f:.2f}"


def _build_macro_for_company() -> dict[str, Any]:
    indicators: list[dict[str, Any]] = []
    for label, series_id in MACRO_SERIES_FOR_COMPANY.items():
        try:
            obs = macro.fetch_observation(series_id)
            indicators.append({"label": label, **obs})
        except Exception as e:
            log.warning(
                "pipeline.context.macro_fetch_failed",
                series_id=series_id,
                error=str(e),
            )
            indicators.append({
                "label": label,
                "series_id": series_id,
                "latest_value": None,
                "latest_date": None,
                "observations": [],
            })
    return {"indicators": indicators}


def build_company_context(ticker: str) -> dict[str, Any]:
    ticker = ticker.upper().strip()
    log.info("pipeline.context.build_company", ticker=ticker)

    edgar_packet = edgar.fetch_packet(ticker)
    quote = market.quote(ticker)
    fundamentals = market.fundamentals(ticker)
    macro_ctx = _build_macro_for_company()

    news_items = news.fetch_recent_news(ticker)
    cik = (edgar_packet or {}).get("cik")
    events = edgar.fetch_material_events(cik, ticker=ticker) if cik else []

    return {
        "ticker": ticker,
        "edgar": edgar_packet,
        "quote": quote,
        "fundamentals": fundamentals,
        "macro": macro_ctx,
        "news": news_items,
        "material_events": events,
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

    fundamentals = ctx.get("fundamentals") or {}
    if fundamentals:
        sections.append("\n## Income statement (yfinance, 4 periods)")
        for row in fundamentals.get("income_stmt", []) or []:
            period = row.get("period", "?")
            lines = []
            for k in _INCOME_KEYS:
                v = row.get(k)
                if v is not None:
                    lines.append(f"    - {k}: {_fmt_billions(v)}")
            if lines:
                sections.append(f"- **{period}**\n" + "\n".join(lines))
        sections.append("\n## Balance sheet (yfinance, 4 periods)")
        for row in fundamentals.get("balance_sheet", []) or []:
            period = row.get("period", "?")
            lines = []
            for k in _BALANCE_KEYS:
                v = row.get(k)
                if v is not None:
                    lines.append(f"    - {k}: {_fmt_billions(v)}")
            if lines:
                sections.append(f"- **{period}**\n" + "\n".join(lines))
        sections.append("\n## Cash flow (yfinance, 4 periods)")
        for row in fundamentals.get("cashflow", []) or []:
            period = row.get("period", "?")
            lines = []
            for k in _CASHFLOW_KEYS:
                v = row.get(k)
                if v is not None:
                    lines.append(f"    - {k}: {_fmt_billions(v)}")
            if lines:
                sections.append(f"- **{period}**\n" + "\n".join(lines))

    if quote:
        sections.append("\n## Market quote (yfinance)")
        for k in ["price", "previous_close", "market_cap", "currency",
                  "trailing_pe", "forward_pe", "price_to_book", "dividend_yield",
                  "beta", "52w_high", "52w_low", "sector", "industry"]:
            v = quote.get(k)
            if v is not None:
                sections.append(f"- {k}: {v}")

    macro_ctx = ctx.get("macro") or {}
    macro_indicators = macro_ctx.get("indicators") or []
    if macro_indicators:
        sections.append("\n## Macro context (FRED)")
        for ind in macro_indicators:
            label = ind.get("label") or ind.get("series_id", "?")
            series_id = ind.get("series_id", "?")
            v = ind.get("latest_value")
            d = ind.get("latest_date") or "?"
            sections.append(f"- {label} ({series_id}): {v} on {d}")

    news_items = ctx.get("news") or []
    if news_items:
        sections.append("\n## Recent market sentiment (yfinance, top 5)")
        for item in news_items:
            date = (item.get("date") or "").strip() or "?"
            title = (item.get("title") or "").strip() or "(untitled)"
            pub = (item.get("publisher") or "").strip()
            link = (item.get("link") or "").strip()
            related = item.get("related_tickers") or []
            summary = (item.get("summary") or "").strip()
            tail = f"  _(related: {', '.join(related)})_" if related else ""
            if pub and link:
                line = f"- **{date}** — {title} — [{pub}]({link}){tail}"
            elif pub:
                line = f"- **{date}** — {title} — {pub}{tail}"
            else:
                line = f"- **{date}** — {title}{tail}"
            sections.append(line)
            if summary:
                sections.append(f"  > {summary}")

    events = ctx.get("material_events") or []
    if events:
        cik = (edgar or {}).get("cik") or ""
        sections.append("\n## Material events (SEC 8-K, impact-ranked, last 24 months)")
        for ev in events:
            tier = ev.get("tier", 3)
            tier_label = {
                1: "TIER 1 (transformational)",
                2: "TIER 2 (significant)",
                3: "TIER 3 (routine)",
            }.get(tier, "TIER ?")
            codes = (ev.get("items") or "").strip()
            descs = [d for d in (ev.get("item_descriptions") or []) if d]
            desc_text = "; ".join(descs) if descs else "(no description)"
            acc = (ev.get("accession") or "").strip()
            date = (ev.get("date") or "").strip() or "?"
            doc = (ev.get("primary_document") or "").strip()
            if acc and cik:
                acc_clean = acc.replace("-", "")
                filing_url = (
                    f"https://www.sec.gov/Archives/edgar/data/"
                    f"{int(cik)}/{acc_clean}/{doc or ''}"
                )
                acc_label = f"[{acc}]({filing_url})"
            else:
                acc_label = acc or "?"
            line = f"- **{date}** — 8-K [{codes}] {desc_text} — {tier_label}"
            if acc:
                line += f" — accession {acc_label}"
            sections.append(line)

    metrics = derive_metrics(fundamentals, quote, edgar.get("facts"))
    if metrics:
        sections.append("\n## Derived metrics")
        sections.append("| Metric | Value | Benchmark | Rating |")
        sections.append("|---|---|---|---|")
        for name in sorted(metrics):
            m = metrics[name]
            label = name.replace("_", " ").title()
            rating = m.get("rating") or "⚪"
            sections.append(f"| {label} | {m['display']} | {m['benchmark']} | {rating} |")

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
