from __future__ import annotations

import datetime as _dt
from typing import Any

import yfinance as yf

from app.logging import get_logger
from app.pipeline import cache
from app.pipeline.edgar import fetch_material_events

log = get_logger(__name__)

_NEWS_TTL_SECONDS = 3600
_NEWS_LIMIT = 5


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

    summary = _coerce_str(inner.get("summary"))

    return {
        "title": title,
        "publisher": publisher,
        "date": date_iso,
        "link": link,
        "related_tickers": [_coerce_str(t) for t in related if _coerce_str(t)][:5],
        "summary": summary,
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


__all__ = ["fetch_recent_news", "fetch_material_events"]
