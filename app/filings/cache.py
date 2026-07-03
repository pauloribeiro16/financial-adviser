"""Permanent JSON cache for 10-K summaries, keyed by (ticker, filing_date)."""

from __future__ import annotations

import json
from pathlib import Path

from app.logging import get_logger
from app.models import FilingSummary

log = get_logger(__name__)

CACHE_ROOT = Path("./data/cache/filings")


def _path(ticker: str, filing_date: str) -> Path:
    return CACHE_ROOT / ticker.upper() / f"{filing_date}_10k_summary.json"


def get(ticker: str, filing_date: str) -> FilingSummary | None:
    p = _path(ticker, filing_date)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return FilingSummary(**data)
    except Exception as e:
        log.warning("filings.cache_read_failed", path=str(p), error=str(e))
        return None


def put(summary: FilingSummary) -> None:
    p = _path(summary.ticker, summary.filing_date)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
    log.info("filings.cache_written", path=str(p))


def latest_filing_date(ticker: str) -> str | None:
    """Return the latest filing_date in cache for given ticker, or None."""
    d = CACHE_ROOT / ticker.upper()
    if not d.exists():
        return None
    dates = sorted(p.name[:10] for p in d.glob("*_10k_summary.json"))
    return dates[-1] if dates else None
