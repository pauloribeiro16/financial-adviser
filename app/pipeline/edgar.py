from __future__ import annotations

import os
from typing import Any

import httpx

from app.logging import get_logger

log = get_logger(__name__)

SEC_BASE = "https://data.sec.gov"
SEC_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
DEFAULT_TIMEOUT = 30.0

_TICKERS_CACHE: dict[str, str] | None = None


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
