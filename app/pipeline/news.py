from __future__ import annotations

import datetime as _dt
from typing import Any

import yfinance as yf

from app.logging import get_logger
from app.pipeline import cache

log = get_logger(__name__)

_NEWS_TTL_SECONDS = 3600
_NEWS_LIMIT = 12
_EVENTS_LIMIT = 15


def _coerce_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    return str(v).strip()


def _normalise_news_item(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None

    inner = raw.get("content") if isinstance(raw.get("content"), dict) else raw

    title = _coerce_str(inner.get("title"))
    if not title:
        return None

    publisher = _coerce_str(inner.get("publisher"))
    if not publisher:
        provider = inner.get("provider")
        if isinstance(provider, dict):
            publisher = _coerce_str(provider.get("displayName")) or _coerce_str(
                provider.get("name")
            )
        elif provider is not None:
            publisher = _coerce_str(provider)

    link = _coerce_str(inner.get("link"))
    if not link:
        for key in ("canonicalUrl", "clickThroughUrl"):
            url_obj = inner.get(key)
            if isinstance(url_obj, dict):
                link = _coerce_str(url_obj.get("url"))
                if link:
                    break
            elif isinstance(url_obj, str):
                link = _coerce_str(url_obj)
                break

    date_iso = ""
    for key in ("pubDate", "displayTime", "publishTime"):
        ts = inner.get(key)
        if isinstance(ts, (int, float)):
            try:
                date_iso = _dt.datetime.fromtimestamp(float(ts), tz=_dt.UTC).strftime(
                    "%Y-%m-%d"
                )
            except (OverflowError, OSError, ValueError):
                date_iso = ""
            if date_iso:
                break
        elif isinstance(ts, str) and ts:
            date_iso = ts[:10]
            break

    if not date_iso:
        ts = raw.get("providerPublishTime")
        if isinstance(ts, (int, float)):
            try:
                date_iso = _dt.datetime.fromtimestamp(float(ts), tz=_dt.UTC).strftime(
                    "%Y-%m-%d"
                )
            except (OverflowError, OSError, ValueError):
                date_iso = ""

    related = inner.get("relatedTickers") or raw.get("relatedTickers") or []
    if not isinstance(related, list):
        related = []

    return {
        "title": title,
        "publisher": publisher,
        "date": date_iso,
        "link": link,
        "related_tickers": [_coerce_str(t) for t in related if _coerce_str(t)][:5],
    }


def fetch_recent_news(ticker: str) -> list[dict[str, Any]]:
    log.info("pipeline.news.fetch", ticker=ticker)
    key = ticker.upper()
    cached = cache.get("news", key, ttl_seconds=_NEWS_TTL_SECONDS)
    if cached is not None:
        return cached.get("items", [])

    items: list[dict[str, Any]] = []
    try:
        raw = yf.Ticker(key).news
        if raw:
            for entry in raw[:_NEWS_LIMIT]:
                norm = _normalise_news_item(entry)
                if norm:
                    items.append(norm)
    except Exception as e:
        log.warning("pipeline.news.fetch_failed", ticker=key, error=str(e)[:200])

    cache.put("news", key, {"items": items})
    return items


def fetch_material_events(cik: str, ticker: str | None = None) -> list[dict[str, Any]]:
    log.info("pipeline.news.material_events", cik=cik, ticker=ticker)
    cache_key = f"events_{ticker.upper()}" if ticker else f"events_{cik}"
    cached = cache.get("news", cache_key, ttl_seconds=_NEWS_TTL_SECONDS)
    if cached is not None:
        return cached.get("items", [])

    items: list[dict[str, Any]] = []
    try:
        from app.pipeline.edgar import company_submissions

        sub = company_submissions(cik)
        recent = sub.get("filings", {}).get("recent", {}) or {}
        forms = recent.get("form", []) or []
        accs = recent.get("accessionNumber", []) or []
        dates = recent.get("filingDate", []) or []
        prims = recent.get("primaryDocument", []) or []
        item_codes = recent.get("items", []) or []
        for i, form in enumerate(forms):
            if not isinstance(form, str) or form not in {"8-K", "8-K/A"}:
                continue
            if len(items) >= _EVENTS_LIMIT:
                break
            code = ""
            if i < len(item_codes) and isinstance(item_codes[i], str):
                code = item_codes[i].strip()
            items.append(
                {
                    "date": dates[i] if i < len(dates) else "",
                    "accession": accs[i] if i < len(accs) else "",
                    "primary_document": prims[i] if i < len(prims) else "",
                    "items": code,
                }
            )
    except Exception as e:
        log.warning("pipeline.news.events_failed", cik=cik, error=str(e)[:200])

    cache.put("news", cache_key, {"items": items})
    return items
