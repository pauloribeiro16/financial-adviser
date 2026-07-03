from __future__ import annotations

from typing import Any

GREEN = "🟢"
YELLOW = "🟡"
RED = "🔴"
NEUTRAL = "⚪"


def _safe_ratio(num: float | None, den: float | None) -> float | None:
    if num is None or den is None:
        return None
    try:
        n = float(num)
        d = float(den)
        if d == 0:
            return None
        return n / d
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _cagr(values: list[float]) -> float | None:
    vals = [v for v in values if v is not None and v > 0]
    if len(vals) < 2:
        return None
    try:
        ratio = vals[-1] / vals[0]
        if ratio <= 0:
            return None
        return ratio ** (1.0 / (len(vals) - 1)) - 1.0
    except Exception:
        return None


def _threshold(
    value: float | None,
    good: float,
    bad: float,
    higher_is_better: bool = True,
) -> str | None:
    if value is None:
        return None
    if higher_is_better:
        if value >= good:
            return GREEN
        if value >= bad:
            return YELLOW
        return RED
    if value <= good:
        return GREEN
    if value <= bad:
        return YELLOW
    return RED


def _fmt_pct(v: float | None) -> str:
    if v is None:
        return "n/a"
    return f"{v * 100:.1f}%"


def _fmt_x(v: float | None) -> str:
    if v is None:
        return "n/a"
    return f"{v:.2f}x"


def _fmt_num(v: float | None) -> str:
    if v is None:
        return "n/a"
    if abs(v) >= 1e9:
        return f"{v / 1e9:.1f}B"
    if abs(v) >= 1e6:
        return f"{v / 1e6:.0f}M"
    return f"{v:.0f}"


def _annual_values(history: list[dict[str, Any]] | None) -> list[float]:
    if not history:
        return []
    seen: set[tuple[str, float]] = set()
    out: list[tuple[str, float]] = []
    for h in history:
        if h.get("form") != "10-K":
            continue
        end = h.get("end") or ""
        val = h.get("val")
        if end and val is not None:
            key = (end, float(val))
            if key in seen:
                continue
            seen.add(key)
            out.append((end, float(val)))
    out.sort(key=lambda x: x[0])
    return [v for _, v in out]


def _latest_annual_value(history: list[dict[str, Any]] | None) -> float | None:
    series = _annual_values(history)
    return series[-1] if series else None


def derive_metrics(
    fundamentals: dict[str, Any] | None,
    quote: dict[str, Any] | None,
    edgar_facts: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Compute derived metrics with benchmarks and traffic-light ratings.

    Returns metric_name → {value, display, benchmark, rating} for every metric
    where the underlying data is present. Missing data ⇒ metric omitted
    silently (caller can detect absence by key not present).
    """
    f = fundamentals or {}
    q = quote or {}
    e = edgar_facts or {}
    out: dict[str, dict[str, Any]] = {}

    income_rows = sorted(f.get("income_stmt") or [], key=lambda r: r.get("period") or "")
    balance_rows = sorted(f.get("balance_sheet") or [], key=lambda r: r.get("period") or "")
    cashflow_rows = sorted(f.get("cashflow") or [], key=lambda r: r.get("period") or "")

    latest_is = income_rows[-1] if income_rows else {}
    latest_bs = balance_rows[-1] if balance_rows else {}
    latest_cf = cashflow_rows[-1] if cashflow_rows else {}
    first_bs = balance_rows[0] if balance_rows else {}

    rev_hist = (e.get("RevenueFromContractWithCustomerExcludingAssessedTax") or {}).get("history_5y") or []
    annual_revs = _annual_values(rev_hist)
    rev_latest = _latest_annual_value(rev_hist) or (e.get("RevenueFromContractWithCustomerExcludingAssessedTax") or {}).get("latest_value")
    op_inc_latest = _latest_annual_value(
        (e.get("OperatingIncomeLoss") or {}).get("history_5y") or []
    ) or (e.get("OperatingIncomeLoss") or {}).get("latest_value")
    net_inc_hist = (e.get("NetIncomeLoss") or {}).get("history_5y") or []
    ni_edgar_latest = _latest_annual_value(net_inc_hist) or (e.get("NetIncomeLoss") or {}).get("latest_value")
    ni_yf = latest_is.get("Net Income From Continuing Operation Net Minority Interest")
    ni = ni_yf if ni_yf is not None else ni_edgar_latest

    if len(annual_revs) >= 2:
        g = _cagr(annual_revs)
        if g is not None:
            out["revenue_growth_3y"] = {
                "value": g,
                "display": _fmt_pct(g),
                "benchmark": ">10% (3y CAGR)",
                "rating": _threshold(g, 0.10, 0.05),
            }

    if op_inc_latest is not None and rev_latest:
        om = _safe_ratio(op_inc_latest, rev_latest)
        if om is not None:
            out["operating_margin"] = {
                "value": om,
                "display": _fmt_pct(om),
                "benchmark": ">15%",
                "rating": _threshold(om, 0.15, 0.08),
            }

    if ni is not None and rev_latest:
        nm = _safe_ratio(ni, rev_latest)
        if nm is not None:
            out["net_margin"] = {
                "value": nm,
                "display": _fmt_pct(nm),
                "benchmark": ">10%",
                "rating": _threshold(nm, 0.10, 0.05),
            }

    ebit = latest_is.get("EBIT")
    tax_rate = latest_is.get("Tax Rate For Calcs")
    invested = latest_bs.get("Invested Capital")
    if ebit is not None and tax_rate is not None and invested:
        nopat = ebit * (1.0 - float(tax_rate))
        roic = _safe_ratio(nopat, invested)
        if roic is not None:
            out["roic"] = {
                "value": roic,
                "display": _fmt_pct(roic),
                "benchmark": ">15%",
                "rating": _threshold(roic, 0.15, 0.08),
            }

    fcf = latest_cf.get("Free Cash Flow")
    if fcf is not None and ni is not None:
        fcf_conv = _safe_ratio(fcf, ni)
        if fcf_conv is not None:
            out["fcf_conversion"] = {
                "value": fcf_conv,
                "display": _fmt_x(fcf_conv),
                "benchmark": ">1x (FCF ≥ NI)",
                "rating": _threshold(fcf_conv, 1.0, 0.7),
            }

    net_debt = latest_bs.get("Net Debt")
    ebitda = latest_is.get("EBITDA") or latest_is.get("Normalized EBITDA")
    if net_debt is not None and ebitda:
        nde = _safe_ratio(net_debt, ebitda)
        if nde is not None:
            out["net_debt_ebitda"] = {
                "value": nde,
                "display": _fmt_x(nde),
                "benchmark": "<2x",
                "rating": _threshold(nde, 2.0, 3.5, higher_is_better=False),
            }

    int_exp = latest_is.get("Interest Expense")
    if ebit is not None and int_exp is not None:
        ic = _safe_ratio(ebit, abs(float(int_exp)))
        if ic is not None:
            out["interest_coverage"] = {
                "value": ic,
                "display": _fmt_x(ic),
                "benchmark": ">10x",
                "rating": _threshold(ic, 10.0, 3.0),
            }

    cash = latest_bs.get("Cash And Cash Equivalents") or latest_cf.get("End Cash Position")
    total_debt = latest_bs.get("Total Debt")
    if cash is not None and total_debt is not None:
        net_cash_v = float(cash) - float(total_debt)
        display = f"{_fmt_num(net_cash_v)} ({'net cash' if net_cash_v > 0 else 'net debt'})"
        if net_cash_v > 0:
            rating = GREEN
        elif net_cash_v > -1e9:
            rating = YELLOW
        else:
            rating = RED
        out["net_cash"] = {
            "value": net_cash_v,
            "display": display,
            "benchmark": ">0 (net cash)",
            "rating": rating,
        }

    shares_first = first_bs.get("Ordinary Shares Number")
    shares_last = latest_bs.get("Ordinary Shares Number")
    if shares_first and shares_last and float(shares_first) > 0:
        delta_pct = (float(shares_last) - float(shares_first)) / float(shares_first)
        out["share_count_change"] = {
            "value": delta_pct,
            "display": _fmt_pct(delta_pct),
            "benchmark": "<0 (decreasing via buybacks)",
            "rating": _threshold(delta_pct, -0.01, 0.02, higher_is_better=False),
        }

    pe = q.get("trailing_pe")
    if pe is not None and float(pe) > 0:
        out["pe"] = {
            "value": float(pe),
            "display": _fmt_x(float(pe)),
            "benchmark": "context-dependent (sector/history)",
            "rating": None,
        }

    pfcf = _safe_ratio(q.get("market_cap"), fcf) if fcf is not None else None
    if pfcf is not None and pfcf > 0:
        out["p_fcf"] = {
            "value": pfcf,
            "display": _fmt_x(pfcf),
            "benchmark": "<20x",
            "rating": _threshold(pfcf, 20.0, 35.0, higher_is_better=False),
        }

    mkt_cap = q.get("market_cap")
    if mkt_cap and net_debt is not None and ebitda:
        ev = float(mkt_cap) + float(net_debt)
        ev_eb = _safe_ratio(ev, ebitda)
        if ev_eb is not None and ev_eb > 0:
            out["ev_ebitda"] = {
                "value": ev_eb,
                "display": _fmt_x(ev_eb),
                "benchmark": "<15x",
                "rating": _threshold(ev_eb, 15.0, 25.0, higher_is_better=False),
            }

    return out
