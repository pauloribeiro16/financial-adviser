from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.logging import get_logger
from app.sectors import IndicatorSpec
from app.watch.aggregator import WatchSummary
from app.watch.reference_reader import DebateRef

log = get_logger(__name__)

GREEN = "🟢"
YELLOW = "🟡"
RED = "🔴"
NA = "n/a"

_MID_TOLERANCE = 0.20


def rate_indicator(spec: IndicatorSpec, value: float | None) -> str:
    if value is None:
        return NA
    try:
        v = float(value)
    except (TypeError, ValueError):
        return NA
    if v != v:
        return NA
    value = v
    healthy = spec.healthy_threshold
    warning = spec.warning_threshold

    if spec.healthier_is == "higher":
        if value >= healthy:
            return GREEN
        if value >= warning:
            return YELLOW
        return RED

    if spec.healthier_is == "lower":
        if value <= healthy:
            return GREEN
        if value <= warning:
            return YELLOW
        return RED

    tol = abs(healthy) * _MID_TOLERANCE if healthy != 0 else _MID_TOLERANCE
    low = healthy - tol
    high = healthy + tol
    if low <= value <= high:
        return GREEN
    upper_extreme = 2.0 * abs(healthy) if healthy != 0 else 2.0 * tol
    if value < low:
        if value >= warning:
            return YELLOW
        return RED
    if value >= upper_extreme:
        return RED
    return YELLOW


def _threshold_text(spec: IndicatorSpec) -> str:
    if spec.healthier_is == "higher":
        return f"\u2265{spec.healthy_threshold:g} healthy / \u2264{spec.warning_threshold:g} warning"
    if spec.healthier_is == "lower":
        return f"\u2264{spec.healthy_threshold:g} healthy / \u2265{spec.warning_threshold:g} warning"
    return (
        f"target {spec.healthy_threshold:g} \u00b1{_MID_TOLERANCE:.0%} "
        f"(\u2264{spec.warning_threshold:g} or \u2265{2 * spec.healthy_threshold:g} warning)"
    )


def _format_value(value: float | None, spec: IndicatorSpec) -> str:
    if value is None:
        return NA
    unit = spec.unit or ""
    if unit == "pct":
        return f"{value * 100:.1f}%"
    if unit == "x":
        return f"{value:.2f}x"
    return f"{value:g}{unit}" if unit else f"{value:g}"


def _safe_dotted(payload: dict[str, Any], path: str) -> float | None:
    cur: Any = payload
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    if cur is None:
        return None
    try:
        v = float(cur)
    except (TypeError, ValueError):
        return None
    if v != v:
        return None
    return v


def _build_indicator_context(ticker: str) -> dict[str, Any]:
    from app.pipeline import cache

    fundamentals = cache.get("fundamentals", ticker.upper(), ttl_seconds=24 * 3600) or {}
    market = cache.get("market", ticker.upper(), ttl_seconds=24 * 3600) or {}
    edgar = cache.get("edgar", ticker.upper(), ttl_seconds=24 * 3600) or {}

    derived: dict[str, float] = {}
    try:
        is_rows = fundamentals.get("income_stmt") or []
        bs_rows = fundamentals.get("balance_sheet") or []
        cf_rows = fundamentals.get("cashflow") or []
        latest_is = is_rows[0] if is_rows else {}
        latest_bs = bs_rows[0] if bs_rows else {}
        latest_cf = cf_rows[0] if cf_rows else {}

        rev = latest_is.get("Total Revenue") or latest_is.get("Operating Revenue")
        op_inc = latest_is.get("EBIT") or latest_is.get("Operating Income")
        gp = latest_is.get("Gross Profit")
        rd = latest_is.get("Research And Development") or latest_is.get("Research Development")
        fcf = latest_cf.get("Free Cash Flow")
        capex = latest_cf.get("Capital Expenditure")
        ebitda = latest_is.get("EBITDA") or latest_is.get("Normalized EBITDA")
        net_debt = latest_bs.get("Net Debt")
        shares_first = (bs_rows[-1] if bs_rows else {}).get("Ordinary Shares Number")
        shares_last = latest_bs.get("Ordinary Shares Number")

        mcap = market.get("market_cap")
        price = market.get("price")
        div_yield = market.get("dividend_yield")

        if fcf is not None and mcap:
            derived["fcf_yield"] = float(fcf) / float(mcap)
        if fcf is not None and rev:
            derived["fcf_margin"] = float(fcf) / float(rev)
        if gp is not None and rev:
            derived["gross_margin"] = float(gp) / float(rev)
        if rev:
            if len(is_rows) >= 2:
                prev = is_rows[1].get("Total Revenue") or is_rows[1].get("Operating Revenue")
                if prev:
                    try:
                        derived["revenue_growth_yoy"] = (float(rev) - float(prev)) / float(prev)
                    except (TypeError, ValueError):
                        pass
        if rd is not None and rev:
            derived["rd_pct_revenue"] = float(rd) / float(rev)
        if capex is not None and rev:
            derived["capex_revenue"] = abs(float(capex)) / float(rev)
        if net_debt is not None and ebitda:
            derived["net_debt_ebitda"] = float(net_debt) / float(ebitda)
        if price and ebitda and net_debt is not None and mcap:
            ev = float(mcap) + float(net_debt)
            derived["ev_ebitda"] = ev / float(ebitda)
        if shares_first and shares_last:
            try:
                derived["share_count_yoy"] = (
                    (float(shares_last) - float(shares_first)) / float(shares_first)
                )
            except (TypeError, ValueError, ZeroDivisionError):
                pass
        if div_yield is not None:
            d = float(div_yield)
            derived["dividend_yield"] = d / 100.0 if d > 1.0 else d
        if op_inc is not None and rev:
            try:
                cur_op = float(op_inc)
                cur_rev = float(rev)
                prev_op = float((is_rows[1] if len(is_rows) >= 2 else {}).get("EBIT") or 0)
                prev_rev = float((is_rows[1] if len(is_rows) >= 2 else {}).get("Total Revenue") or 0)
                if prev_op and prev_rev and cur_rev:
                    d_op = (cur_op - prev_op) / abs(prev_op)
                    d_rev = (cur_rev - prev_rev) / abs(prev_rev)
                    if d_rev != 0:
                        derived["operating_leverage"] = d_op / d_rev
            except (TypeError, ValueError, ZeroDivisionError):
                pass
        derived["net_retention"] = None
        derived["wti_yoy"] = None
    except Exception as e:
        log.warning("watch.markdown_renderer.derive_failed", ticker=ticker, error=str(e))

    return {
        "fundamentals": {**(fundamentals or {}), **derived},
        "market": market or {},
        "edgar": edgar or {},
    }


def indicator_rows_for_ticker(
    ticker: str,
    specs: list[IndicatorSpec],
) -> list[tuple[str, str, str, str]]:
    ctx = _build_indicator_context(ticker)
    rows: list[tuple[str, str, str, str]] = []
    for spec in specs:
        value = _safe_dotted(ctx, spec.extract)
        rating = rate_indicator(spec, value)
        rows.append((spec.name, _format_value(value, spec), rating, _threshold_text(spec)))
    return rows


def fundamentals_dict_for_ticker(
    ticker: str,
    specs: list[IndicatorSpec],
) -> dict[str, float | None]:
    """Build a {indicator_name: raw_value} dict for the aggregator prompt.

    Values are the raw extracted numbers (decimals for pct/x indicators,
    None for missing). The aggregator's ``_format_fundamentals`` handles
    unit-aware formatting and the "n/a" fallback.
    """
    ctx = _build_indicator_context(ticker)
    out: dict[str, float | None] = {}
    for spec in specs:
        out[spec.name] = _safe_dotted(ctx, spec.extract)
    return out


def _trail_rows_for_ticker(
    sector: str,
    ticker: str,
    current_ref: DebateRef,
    base: Path = Path("./out/company"),
) -> list[tuple[str, str, str, float, str]]:
    ticker_dir = base / sector / ticker
    if not ticker_dir.is_dir():
        return []
    rows: list[tuple[str, str, str, float, str]] = []
    current_name = current_ref.debate_path.name
    for p in sorted(ticker_dir.glob("*_debate.md"), key=lambda x: x.stat().st_mtime, reverse=True):
        if p.name == current_name:
            continue
        meta_path = p.with_name(p.name.replace("_debate.md", "_meta.json"))
        date_str = p.stem.split("_")[0]
        provider = p.stem.split("_")[-2] if len(p.stem.split("_")) >= 2 else "?"
        conviction = 0.0
        analysts = "?"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                conviction = float(meta.get("avg_conviction", 0.0) or 0.0)
                analysts_list = meta.get("analysts") or []
                if isinstance(analysts_list, list) and analysts_list:
                    analysts = ", ".join(str(a) for a in analysts_list[:4])
            except Exception:
                pass
        rows.append((date_str, provider, analysts, conviction, str(p)))
    return rows[:8]


def _name_lookup(sector: str, ticker: str) -> str:
    from app.cli_menu import SECTOR_TICKERS
    for sec, lst in SECTOR_TICKERS.items():
        if sec.lower() == sector.lower():
            for sym, name in lst:
                if sym.upper() == ticker.upper():
                    return name
    return ticker.upper()


def _conv_from_summary(summary: WatchSummary) -> float:
    text = (summary.moat + " " + summary.cycle_phase + " " + summary.financial_health).lower()
    if any(kw in text for kw in ("eroding", "weak", "red", "rich", "overvalued")):
        return 0.35
    if any(kw in text for kw in ("🟢", "deep", "compounding", "cheap")):
        return 0.65
    return 0.5


def _verdict_from_summary(summary: WatchSummary) -> str:
    moat = summary.moat.lower()
    risks = summary.risks.lower()
    val = summary.valuation.lower()
    bullish = any(kw in moat for kw in ("🟢", "deep", "widening", "strong", "durable"))
    bearish = any(kw in risks for kw in ("red", "eroding", "shrinking", "weak", "stressed"))
    rich = any(kw in val for kw in ("rich", "overvalued", "expensive"))
    cheap = any(kw in val for kw in ("cheap", "undervalued", "discount"))
    if bullish and not bearish and not rich:
        return "BULLISH"
    if bearish or rich:
        return "BEARISH"
    if cheap and not bearish:
        return "BULLISH"
    return "NEUTRAL"


def render_company_current_md(
    summary: WatchSummary,
    ticker: str,
    sector: str,
    debate_ref: DebateRef,
    indicator_rows: list[tuple[str, str, str, str]],
    buy_price: float,
    sector_target_fcf_yield: float,
    current_price: float,
    *,
    indicator_specs: list[IndicatorSpec] | None = None,
    moat_strength: int | None = None,
) -> str:
    name = _name_lookup(sector, ticker)
    ts = datetime.now().isoformat(timespec="seconds")
    provider = summary.providers_used or debate_ref.meta.get("provider", "unknown")
    session = debate_ref.debate_path.stem

    if current_price and current_price > 0:
        distance_pct = (buy_price - current_price) / current_price
        distance_label = (
            f"{distance_pct * 100:+.1f}% (overvalued)"
            if distance_pct < 0
            else f"{distance_pct * 100:+.1f}% (undervalued)"
        )
    else:
        distance_pct = 0.0
        distance_label = "n/a (missing current price)"

    if indicator_specs and moat_strength is not None:
        spec_legend = ", ".join(
            f"{s.id}={rate_indicator(s, _safe_dotted(_build_indicator_context(ticker), s.extract))}"
            for s in (indicator_specs or [])
        )
    else:
        spec_legend = ""

    lines: list[str] = []
    lines.append(f"# {ticker.upper()} — {name} — {sector}")
    lines.append(
        f"_Last updated: {ts} · Provider: {provider} · Debate session: {session}_"
    )
    lines.append("")
    lines.append("## Summary (5 bullets)")
    lines.append(f"- **Moat:** {summary.moat}")
    lines.append(f"- **Cycle:** {summary.cycle_phase}")
    lines.append(f"- **Financial Health:** {summary.financial_health}")
    lines.append(f"- **Valuation:** {summary.valuation}")
    lines.append(f"- **Risks:** {summary.risks}")
    lines.append("")

    lines.append("## Sector indicators")
    lines.append("| Indicator | Value | Rating | Threshold |")
    lines.append("|---|---|---|---|")
    if not indicator_rows:
        lines.append("| _(none)_ | n/a | n/a | n/a |")
    else:
        for name_, value, rating, thr in indicator_rows:
            lines.append(f"| {name_} | {value} | {rating} | {thr} |")
    lines.append("")

    moat_str = f"moat {moat_strength}" if moat_strength is not None else ""
    margin_str = (
        f"fair \u00d7 {moat_str} \u2192 margin {_margin_for(moat_strength):.2f}"
        if moat_strength is not None
        else "margin 0.85 (default)"
    )
    lines.append("## Buy target")
    lines.append(f"**Buy at:** ${buy_price:,.2f}  ({margin_str})")
    lines.append(f"**Current price:** ${current_price:,.2f}" if current_price else "**Current price:** n/a")
    lines.append(f"**Distance to buy:** {distance_label}")
    lines.append(f"_Sector target FCF yield: {sector_target_fcf_yield:g}_")
    if spec_legend:
        lines.append(f"_Indicator legend: {spec_legend}_")
    lines.append("")

    lines.append("## Trail of debates")
    lines.append("| Date | Provider | Analysts | Conviction | Path |")
    lines.append("|---|---|---|---|---|")
    trail = _trail_rows_for_ticker(sector, ticker, debate_ref)
    if not trail:
        lines.append("| _(none — first watch for this ticker)_ | | | | |")
    else:
        for date_s, prov, analysts, conv, path in trail:
            lines.append(f"| {date_s} | {prov} | {analysts} | {conv:.2f} | `{path}` |")
    lines.append("")
    return "\n".join(lines)


def _margin_for(moat_strength: int | None) -> float:
    from app.watch.price_target import _BASE_MARGIN, _MARGIN_STEP, _MID_MOAT
    if moat_strength is None:
        return _BASE_MARGIN
    return _BASE_MARGIN + _MARGIN_STEP * (moat_strength - _MID_MOAT)


def render_sector_index(
    sector: str,
    entries: list[dict[str, Any]],
) -> str:
    ts = datetime.now().isoformat(timespec="seconds")
    lines: list[str] = []
    lines.append(f"# {sector} — Surveillance {ts}")
    lines.append("")
    lines.append("| Ticker | Name | Verdict | Buy @ | Conviction | Last |")
    lines.append("|---|---|---|---|---|---|")
    if not entries:
        lines.append("| _(no tickers)_ | | | | | |")
    else:
        for e in entries:
            ticker = str(e.get("ticker", "?")).upper()
            name = str(e.get("name", ticker))
            verdict = str(e.get("verdict", "—"))
            buy = e.get("buy_price")
            conv = e.get("conviction")
            last = str(e.get("last_updated", "—"))
            buy_str = f"${buy:,.2f}" if isinstance(buy, (int, float)) and buy else "n/a"
            conv_str = f"{conv:.2f}" if isinstance(conv, (int, float)) else "n/a"
            lines.append(f"| {ticker} | {name} | {verdict} | {buy_str} | {conv_str} | {last} |")
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "rate_indicator",
    "indicator_rows_for_ticker",
    "render_company_current_md",
    "render_sector_index",
    "_verdict_from_summary",
    "_conv_from_summary",
]
