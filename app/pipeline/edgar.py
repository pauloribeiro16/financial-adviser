from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import Any

import httpx

from app.logging import get_logger
from app.pipeline import cache

log = get_logger(__name__)

SEC_BASE = "https://data.sec.gov"
SEC_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
DEFAULT_TIMEOUT = 30.0

_STALE_THRESHOLD_YEARS = 5

_TICKERS_CACHE: dict[str, str] | None = None

_8K_WINDOW_MONTHS = 24
_8K_TIER1_CAP = 6
_8K_TIER2_CAP = 6
_8K_TIER3_CAP = 2
_8K_TIER2_EARNINGS_CAP = 4

_8K_ITEM_TIERS: dict[str, int] = {
    "1.01": 1, "1.02": 1, "1.03": 1,
    "2.01": 1,
    "4.01": 1,
    "4.02": 1,
    "5.02": 1,
    "2.02": 2,
    "5.01": 2,
    "2.05": 2,
    "3.01": 2,
    "8.01": 2,
    "7.01": 3,
    "5.07": 3,
    "5.03": 3,
    "9.01": 3,
    "2.03": 3,
    "2.04": 3,
}

_8K_ITEM_DESCRIPTIONS: dict[str, str] = {
    "1.01": "Material definitive agreement (M&A / major contract)",
    "1.02": "Termination of material definitive agreement",
    "1.03": "Bankruptcy or receivership",
    "2.01": "Completion of acquisition or disposition",
    "2.02": "Results of operations (quarterly earnings)",
    "2.03": "Direct financial obligation",
    "2.04": "Triggering events / debt acceleration",
    "2.05": "Costs associated with exit/restructuring activities",
    "3.01": "Notice of delisting or failure to satisfy continued listing",
    "3.02": "Unregistered sales of equity",
    "3.03": "Material modifications to rights of security holders",
    "4.01": "Changes in registrant's certifying accountant",
    "4.02": "Non-reliance on previously issued financial statements (restatement)",
    "5.01": "Changes in control / election of director",
    "5.02": "Departure of directors or certain officers",
    "5.03": "Amendments to articles of incorporation or bylaws",
    "5.04": "Temporary suspension of trading under employee benefit plans",
    "5.05": "Amendments to the registrant's code of ethics",
    "5.07": "Submission of matters to a vote of security holders",
    "5.08": "Shareholder director nominations",
    "7.01": "Regulation FD disclosure",
    "8.01": "Other events (catch-all material event)",
    "9.01": "Financial statements and exhibits",
}

_TIER_LABELS = {1: "transformational", 2: "significant", 3: "routine"}


def _user_agent() -> str:
    return os.getenv("SEC_USER_AGENT", "financial-adviser dev@example.com")


def _client() -> httpx.Client:
    return httpx.Client(
        headers={
            "User-Agent": _user_agent(),
            "Accept-Encoding": "gzip, deflate",
            "Host": "data.sec.gov",
        },
        timeout=DEFAULT_TIMEOUT,
    )


def _ticker_index() -> dict[str, str]:
    global _TICKERS_CACHE
    if _TICKERS_CACHE is not None:
        return _TICKERS_CACHE
    resp = httpx.get(
        "https://www.sec.gov/files/company_tickers.json",
        headers={"User-Agent": _user_agent()},
        timeout=DEFAULT_TIMEOUT,
    )
    resp.raise_for_status()
    raw = resp.json()
    _TICKERS_CACHE = {v["ticker"].upper(): f"{int(v['cik_str']):010d}" for v in raw.values()}
    return _TICKERS_CACHE


def cik_for_ticker(ticker: str) -> str | None:
    if not ticker:
        return None
    idx = _ticker_index()
    return idx.get(ticker.upper())


def company_submissions(cik: str) -> dict[str, Any]:
    url = f"{SEC_BASE}/submissions/CIK{cik}.json"
    with _client() as c:
        r = c.get(url)
        r.raise_for_status()
        return r.json()


def company_facts(cik: str) -> dict[str, Any]:
    url = f"{SEC_BASE}/api/xbrl/companyfacts/CIK{cik}.json"
    with _client() as c:
        r = c.get(url)
        r.raise_for_status()
        return r.json()


def latest_10k_accession(cik: str) -> dict[str, Any] | None:
    sub = company_submissions(cik)
    recent = sub.get("filings", {}).get("recent", {})
    forms = recent.get("form", []) or []
    accs = recent.get("accessionNumber", []) or []
    dates = recent.get("filingDate", []) or []
    primary = recent.get("primaryDocument", []) or []
    for i, form in enumerate(forms):
        if form in {"10-K", "10-K/A"}:
            return {
                "form": form,
                "accession": accs[i],
                "filing_date": dates[i],
                "primary_document": primary[i],
            }
    return None


def ten_k_url(cik: str, accession: str, primary_document: str) -> str:
    clean_acc = accession.replace("-", "")
    return f"{SEC_ARCHIVES}/{int(cik)}/{clean_acc}/{primary_document}"


def fetch_packet(ticker: str) -> dict[str, Any]:
    """Returns {cik, submissions_summary, facts_summary, latest_10k} or {} on failure."""
    log.info("pipeline.edgar.fetch_packet", ticker=ticker)
    from app.pipeline import cache

    cached = cache.get("edgar", ticker.upper(), ttl_seconds=24 * 3600)
    if cached is not None:
        return cached

    cik = cik_for_ticker(ticker)
    if not cik:
        log.warning("pipeline.edgar.cik_not_found", ticker=ticker)
        return {}

    try:
        sub = company_submissions(cik)
        facts = company_facts(cik)
        ten_k = latest_10k_accession(cik)
    except httpx.HTTPError as e:
        log.warning("pipeline.edgar.http_error", ticker=ticker, error=str(e))
        return {}

    submissions_summary = {
        "name": sub.get("name"),
        "sic": sub.get("sic"),
        "sicDescription": sub.get("sicDescription"),
        "exchanges": sub.get("exchanges"),
        "tickers": sub.get("tickers"),
        "fiscalYearEnd": sub.get("fiscalYearEnd"),
        "stateOfIncorporation": sub.get("stateOfIncorporation"),
    }
    facts_summary = _summarize_facts(facts)
    payload = {
        "cik": cik,
        "ticker": ticker.upper(),
        "submissions": submissions_summary,
        "facts": facts_summary,
        "latest_10k": ten_k,
    }
    cache.put("edgar", ticker.upper(), payload)
    return payload


def _is_stale(period_end: str | None) -> bool:
    if not period_end:
        return False
    try:
        d = datetime.strptime(period_end, "%Y-%m-%d").date()
    except ValueError:
        return False
    cutoff = date.today() - timedelta(days=365 * _STALE_THRESHOLD_YEARS)
    return d < cutoff


def _summarize_facts(facts: dict[str, Any]) -> dict[str, Any]:
    us_gaap = facts.get("facts", {}).get("us-gaap", {}) or {}
    keys = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
            "NetIncomeLoss", "Assets", "Liabilities", "StockholdersEquity",
            "CashAndCashEquivalentsAtCarryingValue", "OperatingIncomeLoss",
            "EarningsPerShareDiluted"]
    summary: dict[str, Any] = {}
    for k in keys:
        node = us_gaap.get(k)
        if not node:
            continue
        units = node.get("units", {})
        for unit_name, series in units.items():
            usd_series = [s for s in series if s.get("form") in {"10-K", "10-Q"}]
            if not usd_series:
                continue
            usd_series.sort(key=lambda s: s.get("end", ""), reverse=True)
            latest = usd_series[0]
            if _is_stale(latest.get("end")):
                continue
            summary[k] = {
                "unit": unit_name,
                "latest_value": latest.get("val"),
                "latest_period_end": latest.get("end"),
                "latest_form": latest.get("form"),
                "fy": latest.get("fy"),
                "fp": latest.get("fp"),
                "history_5y": [
                    {"end": s.get("end"), "val": s.get("val"), "form": s.get("form")}
                    for s in usd_series[:20] if s.get("end", "").startswith(tuple([str(y) for y in range(2019, 2028)]))
                ][:8],
            }
            break
    return summary


def _parse_item_codes(raw: str) -> list[str]:
    if not raw:
        return []
    return [c.strip() for c in raw.split(",") if c.strip()]


def _event_tier(item_codes: list[str]) -> int:
    tiers = [_8K_ITEM_TIERS.get(c, 3) for c in item_codes]
    return min(tiers) if tiers else 3


def _within_window(date_str: str, window_months: int) -> bool:
    if not date_str:
        return False
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
    except ValueError:
        return False
    cutoff = date.today() - timedelta(days=30 * window_months)
    return d >= cutoff


def _earnings_capped(tier2: list[dict[str, Any]]) -> list[dict[str, Any]]:
    earnings = sorted(
        [e for e in tier2 if "2.02" in e["item_codes"]],
        key=lambda e: e["date"],
        reverse=True,
    )[:_8K_TIER2_EARNINGS_CAP]
    non_earnings = [e for e in tier2 if "2.02" not in e["item_codes"]]
    return non_earnings + earnings


def fetch_material_events(cik: str, ticker: str | None = None) -> list[dict[str, Any]]:
    log.info("pipeline.news.material_events", cik=cik, ticker=ticker)
    cache_key = f"events_{ticker.upper()}" if ticker else f"events_{cik}"
    cached = cache.get("news", cache_key, ttl_seconds=3600)
    if cached is not None:
        return cached.get("items", [])

    raw_events: list[dict[str, Any]] = []
    try:
        sub = company_submissions(cik)
        recent = sub.get("filings", {}).get("recent", {}) or {}
        forms = recent.get("form", []) or []
        accs = recent.get("accessionNumber", []) or []
        dates = recent.get("filingDate", []) or []
        prims = recent.get("primaryDocument", []) or []
        item_codes_raw = recent.get("items", []) or []
        for i, form in enumerate(forms):
            if not isinstance(form, str) or form not in {"8-K", "8-K/A"}:
                continue
            if not _within_window(dates[i] if i < len(dates) else "", _8K_WINDOW_MONTHS):
                continue
            raw_codes = (
                item_codes_raw[i]
                if i < len(item_codes_raw) and isinstance(item_codes_raw[i], str)
                else ""
            )
            codes = _parse_item_codes(raw_codes)
            tier = _event_tier(codes)
            raw_events.append({
                "date": dates[i] if i < len(dates) else "",
                "accession": accs[i] if i < len(accs) else "",
                "primary_document": prims[i] if i < len(prims) else "",
                "items": ", ".join(codes),
                "item_codes": codes,
                "tier": tier,
                "item_descriptions": [_8K_ITEM_DESCRIPTIONS.get(c, "") for c in codes],
            })
    except Exception as e:
        log.warning("pipeline.news.events_failed", cik=cik, error=str(e)[:200])

    tier1 = [e for e in raw_events if e["tier"] == 1]
    tier1.sort(key=lambda e: e["date"], reverse=True)
    tier1 = tier1[:_8K_TIER1_CAP]

    tier2_all = [e for e in raw_events if e["tier"] == 2]
    tier2_all.sort(key=lambda e: e["date"], reverse=True)
    tier2_capped = _earnings_capped(tier2_all)
    tier2_capped.sort(key=lambda e: e["date"], reverse=True)
    tier2 = tier2_capped[:_8K_TIER2_CAP]

    tier3 = [e for e in raw_events if e["tier"] == 3]
    tier3.sort(key=lambda e: e["date"], reverse=True)
    tier3 = tier3[:_8K_TIER3_CAP]

    selected = tier1 + tier2 + tier3
    cache.put("news", cache_key, {"items": selected})
    return selected
