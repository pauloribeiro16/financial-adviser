from __future__ import annotations

from typing import Any

import httpx

from app.logging import get_logger

log = get_logger(__name__)

FRED_BASE = "https://api.stlouisfed.org"
FALLBACK_OBS_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
TIMEOUT = 30.0


def fetch_observation(series_id: str, as_of: str | None = None) -> dict[str, Any]:
    """Returns latest FRED observation for a series.

    Falls back to public CSV endpoint if FRED API key is not configured.
    `as_of` accepts YYYY-MM-DD; if omitted, returns the most recent observation.
    """
    log.info("pipeline.macro.fetch_observation", series_id=series_id, as_of=as_of)
    from app.pipeline import cache

    cached = cache.get("fred", series_id, ttl_seconds=6 * 3600)
    if cached is not None:
        return _maybe_filter_date(cached, as_of)

    api_key = __import__("os").environ.get("FRED_API_KEY")
    payload = _fetch_with_api_key(series_id, api_key) if api_key else _fetch_csv_fallback(series_id)
    if payload is None:
        return {"series_id": series_id, "latest_value": None, "observations": [], "as_of": as_of}

    cache.put("fred", series_id, payload)
    return _maybe_filter_date(payload, as_of)


def _maybe_filter_date(payload: dict[str, Any], as_of: str | None) -> dict[str, Any]:
    if not as_of:
        return payload
    obs = payload.get("observations", []) or []
    filtered = [o for o in obs if o.get("date", "") <= as_of]
    if not filtered:
        return {**payload, "latest_value": None, "as_of": as_of}
    latest = filtered[0]
    return {**payload, "latest_value": latest.get("value"), "as_of": as_of, "observations": filtered[:8]}


def _fetch_with_api_key(series_id: str, api_key: str) -> dict[str, Any] | None:
    url = f"{FRED_BASE}/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 24,
    }
    try:
        r = httpx.get(url, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        obs = [
            {"date": o["date"], "value": float(o["value"]) if o["value"] not in (".", "") else None}
            for o in data.get("observations", [])
        ]
        obs = [o for o in obs if o["value"] is not None]
        return {
            "series_id": series_id,
            "latest_value": obs[0]["value"] if obs else None,
            "latest_date": obs[0]["date"] if obs else None,
            "observations": obs,
        }
    except Exception as e:
        log.warning("pipeline.macro.fred_api_failed", series_id=series_id, error=str(e))
        return None


def _fetch_csv_fallback(series_id: str) -> dict[str, Any] | None:
    try:
        r = httpx.get(
            FALLBACK_OBS_URL,
            params={"id": series_id},
            headers={"User-Agent": "financial-adviser/0.1"},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        lines = [ln for ln in r.text.splitlines() if ln.strip()]
        if len(lines) < 2:
            return None
        obs = []
        for ln in lines[1:]:
            parts = ln.split(",")
            if len(parts) != 2:
                continue
            try:
                val = float(parts[1])
            except ValueError:
                continue
            obs.append({"date": parts[0], "value": val})
        obs.reverse()
        obs = obs[-24:]
        return {
            "series_id": series_id,
            "latest_value": obs[-1]["value"] if obs else None,
            "latest_date": obs[-1]["date"] if obs else None,
            "observations": obs,
        }
    except Exception as e:
        log.warning("pipeline.macro.fred_csv_failed", series_id=series_id, error=str(e))
        return None
