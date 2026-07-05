from __future__ import annotations

from pathlib import Path

import pytest

from app.filings.cache import _path, get, latest_filing_date, put
from app.models import FilingSummary


@pytest.fixture
def temp_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr("app.filings.cache.CACHE_ROOT", tmp_path)
    return tmp_path


def _sample(ticker: str = "XOM", filing_date: str = "2025-12-31") -> FilingSummary:
    return FilingSummary(
        ticker=ticker,
        filing_date=filing_date,
        form="10-K",
        business_and_market_risk="oil and gas exploration",
        risk_factors="commodity price exposure",
        md_and_a="revenue grew year over year",
    )


def test_get_nonexistent_returns_none(temp_cache: Path) -> None:
    assert get("XOM", "2025-12-31") is None


def test_put_then_get_roundtrip(temp_cache: Path) -> None:
    put(_sample())
    r = get("XOM", "2025-12-31")
    assert r is not None
    assert r.ticker == "XOM"
    assert r.form == "10-K"
    assert r.business_and_market_risk == "oil and gas exploration"
    assert r.risk_factors == "commodity price exposure"


def test_path_helper(temp_cache: Path) -> None:
    p = _path("xom", "2025-12-31")
    assert p.name == "2025-12-31_10k_summary.json"
    assert p.parent.name == "XOM"


def test_latest_filing_date_empty(temp_cache: Path) -> None:
    assert latest_filing_date("XOM") is None


def test_latest_filing_date_returns_max(temp_cache: Path) -> None:
    put(_sample(ticker="AAPL", filing_date="2023-12-31"))
    put(_sample(ticker="AAPL", filing_date="2024-12-31"))
    put(_sample(ticker="AAPL", filing_date="2024-06-30"))
    assert latest_filing_date("AAPL") == "2024-12-31"


def test_put_writes_under_uppercase_ticker_dir(temp_cache: Path) -> None:
    put(_sample(ticker="xom", filing_date="2025-12-31"))
    assert (temp_cache / "XOM" / "2025-12-31_10k_summary.json").exists()


def test_get_handles_malformed_json(temp_cache: Path) -> None:
    p = _path("XOM", "2025-12-31")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{not valid json", encoding="utf-8")
    assert get("XOM", "2025-12-31") is None


def test_get_handles_wrong_schema(temp_cache: Path) -> None:
    p = _path("XOM", "2025-12-31")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{"ticker": "XOM", "filing_date": "2025-12-31"}', encoding="utf-8")
    assert get("XOM", "2025-12-31") is None
