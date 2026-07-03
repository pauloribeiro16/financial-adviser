from __future__ import annotations

import json
import os

from app.pipeline.context import build_company_context, render_context_markdown
from app.pipeline.metrics import derive_metrics

REPO_ROOT = "/Users/pauloribeiro/Desktop/Projetos/financial-adviser"
MSFT_TICKER = "MSFT"


def _load_msft_data() -> tuple[dict, dict, dict]:
    h: str | None = None
    for fn in os.listdir(f"{REPO_ROOT}/data/cache/market"):
        p = f"{REPO_ROOT}/data/cache/market/{fn}"
        d = json.load(open(p))
        if d.get("long_name") == "Microsoft Corporation":
            h = fn.replace(".json", "")
            break
    assert h is not None, "MSFT cache not found"
    fund = json.load(open(f"{REPO_ROOT}/data/cache/fundamentals/{h}.json"))
    quote = json.load(open(f"{REPO_ROOT}/data/cache/market/{h}.json"))
    edgar = json.load(open(f"{REPO_ROOT}/data/cache/edgar/{h}.json"))
    return fund, quote, edgar


def test_derive_metrics_msft_returns_all_computable_metrics() -> None:
    fund, quote, edgar = _load_msft_data()
    m = derive_metrics(fund, quote, edgar.get("facts"))
    required = {
        "operating_margin", "net_margin", "roic",
        "fcf_conversion", "net_debt_ebitda", "interest_coverage",
        "net_cash", "share_count_change", "pe",
    }
    missing = required - set(m)
    assert not missing, f"missing required metrics: {missing}"
    for k in required:
        v = m[k]
        assert "value" in v and "display" in v and "rating" in v
        assert v["rating"] in ("🟢", "🟡", "🔴", None), (k, v)
    roic = m["roic"]["value"]
    assert 0.05 < roic < 0.60, f"ROIC sanity out of range: {roic}"
    print("OK; MSFT metrics present:", sorted(m))


def test_derive_metrics_handles_empty_inputs() -> None:
    assert derive_metrics(None, None, None) == {}
    assert derive_metrics({}, {}, {}) == {}
    print("OK; empty inputs return empty dict")


def test_derive_metrics_ratings_in_valid_set() -> None:
    fund, quote, edgar = _load_msft_data()
    m = derive_metrics(fund, quote, edgar.get("facts"))
    valid = {"🟢", "🟡", "🔴", "⚪", None}
    for k, v in m.items():
        assert v["rating"] in valid, (k, v["rating"])
    print("OK; all ratings in", valid)


def test_derive_metrics_partial_inputs_skip_gracefully() -> None:
    fund, quote, edgar = _load_msft_data()
    m_no_fund = derive_metrics(None, quote, edgar.get("facts"))
    m_no_quote = derive_metrics(fund, None, edgar.get("facts"))
    m_no_edgar = derive_metrics(fund, quote, None)
    assert "roic" not in m_no_fund
    assert "pe" not in m_no_quote
    assert "operating_margin" not in m_no_edgar
    for partial in (m_no_fund, m_no_quote, m_no_edgar):
        for _k, v in partial.items():
            assert v["rating"] in {"🟢", "🟡", "🔴", "⚪", None}
    print("OK; partial inputs skip missing metrics gracefully")


def test_rendered_context_includes_derived_metrics_section() -> None:
    os.environ.pop("LANGFUSE_PUBLIC_KEY", None)
    os.environ.pop("LANGFUSE_SECRET_KEY", None)
    ctx = build_company_context(MSFT_TICKER)
    md = render_context_markdown(ctx, "company")
    assert "## Derived metrics" in md
    assert "| Metric | Value | Benchmark | Rating |" in md
    assert "Roic" in md
    assert "Net Debt Ebitda" in md
    assert "🟢" in md or "🟡" in md or "🔴" in md, "expected at least one traffic-light rating"
    print("OK; derived metrics rendered as table")
