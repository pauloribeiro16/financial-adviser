"""Tests for app.filings.summarizer."""

from __future__ import annotations

import httpx
import pytest

from app.filings import cache, summarizer
from app.filings.summarizer import (
    _chunk_text,
    _summarize_section,
    _word_count,
    get_or_build_summary,
    summarize_sections,
)
from app.models import FilingSummary
from app.providers import ProviderRegistry


def test_word_count() -> None:
    assert _word_count("") == 0
    assert _word_count("a b c") == 3
    assert _word_count("  spaced  out  ") == 2


def test_chunk_text_short_returns_single_chunk() -> None:
    text = " ".join(f"w{i}" for i in range(50))
    assert _chunk_text(text, chunk_words=100, overlap_words=10) == [text]


def test_chunk_text_long_multiple_chunks_cover_all_words() -> None:
    text = " ".join(f"w{i}" for i in range(2500))
    chunks = _chunk_text(text, chunk_words=1000, overlap_words=100)
    assert len(chunks) > 1
    seen = {w for c in chunks for w in c.split()}
    assert seen == set(text.split())


def test_summarize_sections_with_mock_returns_filing_summary() -> None:
    s = summarize_sections(
        {"business": "Apple designs smartphones.", "risk_factors": "Supply chain.",
         "md_and_a": "Revenue grew 12% YoY.", "market_risk": "FX exposure."},
        ticker="AAPL", provider_name="mock",
    )
    assert isinstance(s, FilingSummary)
    assert s.ticker == "AAPL" and s.form == "10-K" and s.filing_date == ""
    for f in (s.business_and_market_risk, s.risk_factors, s.md_and_a):
        assert f is not None and len(f) <= 500


def test_summarize_section_long_text_uses_map_reduce(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake(provider: object, sp: str, *, ticker: str, label: str) -> str:
        calls.append(label)
        return f"p-{len(calls)}"

    monkeypatch.setattr(summarizer, "_call_llm", fake)
    result = _summarize_section(
        ProviderRegistry.get("mock"),
        " ".join(f"w{i}" for i in range(20000)),
        "{text}", ticker="T", label="long",
    )
    assert len(calls) > 1 and any("_consolidate" in c for c in calls) and result


def test_get_or_build_summary_cache_hit(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cache, "CACHE_ROOT", tmp_path)
    cache.put(FilingSummary(
        ticker="AAPL", filing_date="2024-12-31", form="10-K",
        business_and_market_risk="cached", risk_factors="r", md_and_a="m",
    ))
    called = {"v": False}
    monkeypatch.setattr(
        "app.filings.summarizer.download_10k_html",
        lambda *a, **kw: called.update(v=True) or "",
    )
    result = get_or_build_summary("AAPL", "mock")
    assert result is not None and result.filing_date == "2024-12-31"
    assert result.business_and_market_risk == "cached" and called["v"] is False


def test_get_or_build_summary_cache_miss_triggers_download(
    tmp_path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cache, "CACHE_ROOT", tmp_path)
    monkeypatch.setattr("app.filings.summarizer.cik_for_ticker", lambda t: "0000320193")
    ten_k = {"form": "10-K", "accession": "0000320193-24-000123",
             "filing_date": "2024-12-31", "primary_document": "aapl.htm"}
    monkeypatch.setattr("app.filings.summarizer.latest_10k_accession", lambda c: ten_k)
    called = {"v": False}
    html = (
        "Item 1. Business " + ("Apple designs consumer electronics. " * 20)
        + "Item 1A. Risk Factors " + ("Supply chain disruption. " * 20)
        + "Item 7. Management's Discussion and Analysis " + ("Revenue grew 12% year over year. " * 20)
        + "Item 7A. Quantitative and Qualitative Disclosures About Market Risk "
        + ("Foreign exchange exposure to EUR. " * 20)
    )
    monkeypatch.setattr(
        "app.filings.summarizer.download_10k_html",
        lambda c, a, p: called.update(v=True) or html,
    )
    result = get_or_build_summary("AAPL", "mock")
    assert called["v"] is True and result is not None
    assert result.ticker == "AAPL" and result.filing_date == "2024-12-31"
    assert (tmp_path / "AAPL" / "2024-12-31_10k_summary.json").exists()


def test_get_or_build_summary_no_cik_or_http_error(
    tmp_path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.filings.summarizer.cik_for_ticker", lambda t: None)
    assert get_or_build_summary("ZZZZ", "mock") is None
    monkeypatch.setattr(cache, "CACHE_ROOT", tmp_path)
    monkeypatch.setattr("app.filings.summarizer.cik_for_ticker", lambda t: "0000320193")
    ten_k = {"form": "10-K", "accession": "0000320193-24-000123",
             "filing_date": "2024-12-31", "primary_document": "aapl.htm"}
    monkeypatch.setattr("app.filings.summarizer.latest_10k_accession", lambda c: ten_k)

    def boom(c: str, a: str, p: str) -> str:
        raise httpx.HTTPError("boom")

    monkeypatch.setattr("app.filings.summarizer.download_10k_html", boom)
    assert get_or_build_summary("AAPL", "mock") is None
