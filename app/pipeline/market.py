from __future__ import annotations

from typing import Any

import yfinance as yf

from app.logging import get_logger

log = get_logger(__name__)


def quote(ticker: str) -> dict[str, Any]:
    log.info("pipeline.market.quote", ticker=ticker)
    from app.pipeline import cache

    cached = cache.get("market", ticker.upper(), ttl_seconds=15 * 60)
    if cached is not None:
        return cached

    t = yf.Ticker(ticker.upper())
    try:
        fast_info = t.fast_info
        price = getattr(fast_info, "last_price", None) or getattr(fast_info, "previous_close", None)
        mcap = getattr(fast_info, "market_cap", None)
        payload = {
            "price": price,
            "previous_close": getattr(fast_info, "previous_close", None),
            "market_cap": mcap,
            "currency": getattr(fast_info, "currency", None),
            "year_high": getattr(fast_info, "year_high", None),
            "year_low": getattr(fast_info, "year_low", None),
        }
    except Exception as e:
        log.warning("pipeline.market.fast_info_failed", ticker=ticker, error=str(e))
        payload = {"price": None, "previous_close": None, "market_cap": None}

    try:
        info = t.info or {}
        payload.update({
            "long_name": info.get("longName"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "country": info.get("country"),
            "currency_info": info.get("currency"),
            "shares_outstanding": info.get("sharesOutstanding"),
            "trailing_pe": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "price_to_book": info.get("priceToBook"),
            "dividend_yield": info.get("dividendYield"),
            "beta": info.get("beta"),
            "52w_high": info.get("fiftyTwoWeekHigh"),
            "52w_low": info.get("fiftyTwoWeekLow"),
        })
    except Exception as e:
        log.warning("pipeline.market.info_failed", ticker=ticker, error=str(e))

    cache.put("market", ticker.upper(), payload)
    return payload


def fundamentals(ticker: str) -> dict[str, Any]:
    log.info("pipeline.market.fundamentals", ticker=ticker)
    from app.pipeline import cache

    cached = cache.get("fundamentals", ticker.upper(), ttl_seconds=24 * 3600)
    if cached is not None:
        return cached

    t = yf.Ticker(ticker.upper())
    out: dict[str, Any] = {}

    for attr, label in [
        ("income_stmt", "income_stmt"),
        ("balance_sheet", "balance_sheet"),
        ("cashflow", "cashflow"),
    ]:
        try:
            df = getattr(t, attr, None)
            if df is not None and not df.empty:
                rows = []
                for col in df.columns[:6]:
                    row = {"period": str(col)}
                    for idx in df.index[:12]:
                        val = df.loc[idx, col]
                        if hasattr(val, "item"):
                            val = val.item()
                        if val is not None and not (isinstance(val, float) and val != val):
                            row[str(idx)] = val
                    rows.append(row)
                out[label] = rows
        except Exception as e:
            log.warning("pipeline.market.attr_failed", ticker=ticker, attr=attr, error=str(e))

    cache.put("fundamentals", ticker.upper(), out)
    return out
