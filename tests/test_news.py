from __future__ import annotations

from unittest.mock import patch

import pytest

from app.pipeline import cache, news
from app.pipeline.context import build_company_context, render_context_markdown

REPO_ROOT = "/Users/pauloribeiro/Desktop/Projetos/financial-adviser"
MSFT_TICKER = "MSFT"
MSFT_CIK = "0000789019"


@pytest.fixture(autouse=True)
def _clear_news_cache():
    ns = cache.CACHE_DIR / "news"
    if ns.exists():
        for f in ns.iterdir():
            try:
                f.unlink()
            except FileNotFoundError:
                pass
    yield

NEW_SHAPE_SAMPLE = [
    {
        "id": "abc-1",
        "content": {
            "id": "abc-1",
            "contentType": "STORY",
            "title": "Sample headline about MSFT earnings",
            "pubDate": "2026-07-02T13:51:25Z",
            "displayTime": "2026-07-02T13:51:25Z",
            "provider": {"displayName": "Yahoo Finance", "url": "http://finance.yahoo.com/"},
            "canonicalUrl": {"url": "https://finance.yahoo.com/article/msft-x"},
        },
    },
    {
        "id": "abc-2",
        "content": {
            "title": "Older article",
            "pubDate": "2026-06-20T09:00:00Z",
            "provider": {"displayName": "Reuters"},
            "canonicalUrl": {"url": "https://reuters.com/article-2"},
        },
    },
]

OLD_SHAPE_SAMPLE = [
    {
        "title": "Legacy article",
        "publisher": "Bloomberg",
        "link": "https://bloomberg.com/article",
        "providerPublishTime": 1721000000,
        "relatedTickers": ["MSFT", "AAPL"],
    },
]


def test_fetch_recent_news_returns_list() -> None:
    items = news.fetch_recent_news(MSFT_TICKER)
    assert isinstance(items, list)
    for item in items:
        assert isinstance(item, dict)
        assert "title" in item
        assert isinstance(item["title"], str) and item["title"]


def test_fetch_recent_news_shape_new_envelope() -> None:
    with patch("app.pipeline.news.yf.Ticker") as mock_ticker:
        mock_ticker.return_value.news = NEW_SHAPE_SAMPLE
        items = news.fetch_recent_news(MSFT_TICKER)
    assert len(items) == 2
    first = items[0]
    assert first["title"] == "Sample headline about MSFT earnings"
    assert first["publisher"] == "Yahoo Finance"
    assert first["date"] == "2026-07-02"
    assert first["link"] == "https://finance.yahoo.com/article/msft-x"
    second = items[1]
    assert second["publisher"] == "Reuters"
    assert second["date"] == "2026-06-20"


def test_fetch_recent_news_shape_legacy() -> None:
    with patch("app.pipeline.news.yf.Ticker") as mock_ticker:
        mock_ticker.return_value.news = OLD_SHAPE_SAMPLE
        items = news.fetch_recent_news(MSFT_TICKER)
    assert len(items) == 1
    first = items[0]
    assert first["title"] == "Legacy article"
    assert first["publisher"] == "Bloomberg"
    assert first["link"] == "https://bloomberg.com/article"
    assert first["date"] == "2024-07-14"
    assert first["related_tickers"] == ["MSFT", "AAPL"]


def test_fetch_recent_news_uses_cache() -> None:
    with patch("app.pipeline.news.yf.Ticker") as mock_ticker:
        mock_ticker.return_value.news = NEW_SHAPE_SAMPLE
        first = news.fetch_recent_news(MSFT_TICKER)
        second = news.fetch_recent_news(MSFT_TICKER)
        assert mock_ticker.call_count == 1
    assert first == second


def test_fetch_recent_news_handles_failure() -> None:
    class _Boom:
        @property
        def news(self):
            raise RuntimeError("boom")

    with patch("app.pipeline.news.yf.Ticker", return_value=_Boom()):
        items = news.fetch_recent_news(MSFT_TICKER)
    assert items == []


def test_fetch_recent_news_handles_missing_ticker() -> None:
    with patch("app.pipeline.news.yf.Ticker") as mock_ticker:
        mock_ticker.return_value.news = []
        items = news.fetch_recent_news("NOPE_NOT_REAL_999")
    assert items == []


def test_fetch_material_events_returns_8k_only() -> None:
    events = news.fetch_material_events(MSFT_CIK, MSFT_TICKER)
    assert isinstance(events, list)
    for ev in events:
        assert "date" in ev
        assert "accession" in ev
        assert "primary_document" in ev
        assert "items" in ev


def test_fetch_material_events_filters_non_8k() -> None:
    fake_submissions = {
        "filings": {
            "recent": {
                "form": ["10-K", "8-K", "10-Q", "8-K/A", "4", "8-K"],
                "accessionNumber": [
                    "0001-10K",
                    "0001-8K1",
                    "0001-10Q",
                    "0001-8KA",
                    "0001-form4",
                    "0001-8K2",
                ],
                "filingDate": ["2026-01-01", "2026-02-01", "2026-03-01", "2026-04-01", "2026-05-01", "2026-06-01"],
                "primaryDocument": ["a.htm", "b.htm", "c.htm", "d.htm", "e.htm", "f.htm"],
                "items": ["", "5.02", "", "2.01,5.02", "", "7.01"],
            }
        }
    }
    with patch("app.pipeline.edgar.company_submissions", return_value=fake_submissions):
        events = news.fetch_material_events("0000789019", "MSFT")
    forms_seen = [ev["accession"] for ev in events]
    assert forms_seen == ["0001-8K1", "0001-8KA", "0001-8K2"]
    assert events[0]["items"] == "5.02"
    assert events[1]["items"] == "2.01,5.02"
    assert events[2]["items"] == "7.01"


def test_fetch_material_events_handles_missing_items() -> None:
    fake_submissions = {
        "filings": {
            "recent": {
                "form": ["8-K"],
                "accessionNumber": ["0001-8K"],
                "filingDate": ["2026-02-01"],
                "primaryDocument": ["x.htm"],
            }
        }
    }
    with patch("app.pipeline.edgar.company_submissions", return_value=fake_submissions):
        events = news.fetch_material_events("0000789019", "MSFT")
    assert len(events) == 1
    assert events[0]["items"] == ""
    assert events[0]["date"] == "2026-02-01"


def test_fetch_material_events_handles_failure() -> None:
    with patch(
        "app.pipeline.edgar.company_submissions",
        side_effect=RuntimeError("sec down"),
    ):
        events = news.fetch_material_events("0000789019", "MSFT")
    assert events == []


def test_rendered_context_includes_news_sections() -> None:
    ctx = build_company_context(MSFT_TICKER)
    assert "news" in ctx, "ctx missing 'news' key"
    assert "material_events" in ctx, "ctx missing 'material_events' key"
    md = render_context_markdown(ctx, "company")
    assert "## Recent news" in md, "Recent news section missing in render"
    assert "## Material events" in md, "Material events section missing in render"


def test_rendered_news_section_lists_titles() -> None:
    with patch("app.pipeline.news.yf.Ticker") as mock_ticker:
        mock_ticker.return_value.news = NEW_SHAPE_SAMPLE
        ctx = build_company_context(MSFT_TICKER)
    md = render_context_markdown(ctx, "company")
    assert "Sample headline about MSFT earnings" in md
    assert "Yahoo Finance" in md
    news_block = md.split("## Recent news", 1)[1].split("## ", 1)[0]
    assert news_block.count("- **") >= 2


def test_rendered_material_events_lists_items() -> None:
    fake_submissions = {
        "filings": {
            "recent": {
                "form": ["8-K"],
                "accessionNumber": ["0001-8K-FAKE"],
                "filingDate": ["2026-02-01"],
                "primaryDocument": ["x.htm"],
                "items": ["2.02"],
            }
        }
    }
    with patch("app.pipeline.edgar.company_submissions", return_value=fake_submissions):
        ctx = build_company_context(MSFT_TICKER)
    md = render_context_markdown(ctx, "company")
    assert "8-K (items: 2.02)" in md
    assert "0001-8K-FAKE" in md
    assert "https://www.sec.gov/Archives/edgar/data/" in md


def test_rendered_context_omits_news_when_empty() -> None:
    with patch("app.pipeline.news.yf.Ticker") as mock_ticker:
        mock_ticker.return_value.news = []
        ctx = build_company_context(MSFT_TICKER)
    md = render_context_markdown(ctx, "company")
    assert "## Recent news" not in md
