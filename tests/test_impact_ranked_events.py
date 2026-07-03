from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

import pytest

from app.pipeline import cache, news
from app.pipeline.context import build_company_context, render_context_markdown
from app.pipeline.edgar import (
    _8K_ITEM_DESCRIPTIONS,
    _8K_ITEM_TIERS,
    _event_tier,
    _within_window,
    fetch_material_events,
)

REPO_ROOT = Path("/Users/pauloribeiro/Desktop/Projetos/financial-adviser")
JPM_TICKER = "JPM"
JPM_CIK = "0000019617"


@pytest.fixture(autouse=True)
def _clear_news_cache() -> None:
    ns = cache.CACHE_DIR / "news"
    if ns.exists():
        for f in ns.iterdir():
            try:
                f.unlink()
            except FileNotFoundError:
                pass
    yield


def test_tier_map_constants() -> None:
    assert _8K_ITEM_TIERS["1.01"] == 1
    assert _8K_ITEM_TIERS["1.02"] == 1
    assert _8K_ITEM_TIERS["1.03"] == 1
    assert _8K_ITEM_TIERS["2.01"] == 1
    assert _8K_ITEM_TIERS["4.01"] == 1
    assert _8K_ITEM_TIERS["4.02"] == 1
    assert _8K_ITEM_TIERS["5.02"] == 1
    assert _8K_ITEM_TIERS["2.02"] == 2
    assert _8K_ITEM_TIERS["5.01"] == 2
    assert _8K_ITEM_TIERS["8.01"] == 2
    assert _8K_ITEM_TIERS["7.01"] == 3
    assert _8K_ITEM_TIERS["5.07"] == 3
    assert _8K_ITEM_TIERS["9.01"] == 3
    assert "5.02" in _8K_ITEM_DESCRIPTIONS
    assert "Officer" in _8K_ITEM_DESCRIPTIONS["5.02"] or "officer" in _8K_ITEM_DESCRIPTIONS["5.02"]


def test_event_tier_highest_among_codes() -> None:
    assert _event_tier(["7.01", "5.02"]) == 1
    assert _event_tier(["5.02", "9.01"]) == 1
    assert _event_tier(["2.02", "9.01"]) == 2
    assert _event_tier(["2.02", "7.01"]) == 2
    assert _event_tier([]) == 3
    assert _event_tier(["9.01"]) == 3
    assert _event_tier(["7.01"]) == 3
    assert _event_tier([""]) == 3
    assert _event_tier(["99.99"]) == 3


def test_within_window() -> None:
    assert _within_window("2026-07-03", 24) is True
    assert _within_window("2025-01-01", 24) is True
    assert _within_window("2020-01-01", 24) is False
    assert _within_window("2022-01-01", 24) is False
    assert _within_window("", 24) is False
    assert _within_window("not-a-date", 24) is False


def test_fetch_material_events_jpm_returns_impact_ranked() -> None:
    events = fetch_material_events(JPM_CIK, JPM_TICKER)
    assert isinstance(events, list)
    assert len(events) > 0, "expected at least one ranked 8-K event for JPM"

    for ev in events:
        assert "tier" in ev, f"event missing tier field: {ev}"
        assert ev["tier"] in (1, 2, 3)
        assert "item_codes" in ev
        assert "item_descriptions" in ev
        assert "date" in ev
        assert "accession" in ev

    tiers = [ev["tier"] for ev in events]
    assert tiers == sorted(tiers), f"events not tier-sorted ascending: {tiers}"

    has_tier1_5_02 = any(
        ev["tier"] == 1 and "5.02" in ev["item_codes"]
        for ev in events
    )
    assert has_tier1_5_02, (
        f"expected at least one Tier 1 event with item 5.02 (officer departure); "
        f"got tiers={tiers}, codes={[ev['item_codes'] for ev in events]}"
    )

    tier3_codes = [ev for ev in events if ev["tier"] == 3]
    assert len(tier3_codes) <= 2, f"Tier 3 cap violated: {len(tier3_codes)} events"

    earnings = [ev for ev in events if ev["tier"] == 2 and "2.02" in ev["item_codes"]]
    assert len(earnings) <= 4, (
        f"earnings 2.02 cap violated: {len(earnings)} events"
    )

    tier2_total = sum(1 for ev in events if ev["tier"] == 2)
    assert tier2_total <= 6, f"Tier 2 cap violated: {tier2_total} events"

    tier1_total = sum(1 for ev in events if ev["tier"] == 1)
    assert tier1_total <= 6, f"Tier 1 cap violated: {tier1_total} events"


def test_fetch_material_events_includes_old_impactful_event() -> None:
    """An 18-month-old Tier 1 event must appear in the result, proving that
    impact (not recency) drives selection — a 1-month-old Tier 3 routine
    event must NOT displace it."""
    eighteen_months_ago = "2025-01-03"
    one_month_ago = "2026-06-03"
    fake_submissions = {
        "filings": {
            "recent": {
                "form": ["8-K", "8-K", "8-K"],
                "accessionNumber": ["RECENT-7.01", "OLD-5.02", "ANCIENT-9.01"],
                "filingDate": [one_month_ago, eighteen_months_ago, "2023-01-01"],
                "primaryDocument": ["r.htm", "o.htm", "a.htm"],
                "items": ["7.01", "5.02", "9.01"],
            }
        }
    }
    with patch("app.pipeline.edgar.company_submissions", return_value=fake_submissions):
        events = fetch_material_events("0000019617", "JPM")

    by_acc = {ev["accession"]: ev for ev in events}
    assert "OLD-5.02" in by_acc, (
        f"18-month-old Tier 1 (5.02) event must be selected; got accs="
        f"{list(by_acc.keys())}"
    )
    assert "ANCIENT-9.01" not in by_acc, (
        "out-of-window event must be filtered out"
    )
    assert by_acc["OLD-5.02"]["tier"] == 1
    assert by_acc["RECENT-7.01"]["tier"] == 3


def test_news_limit_is_5() -> None:
    assert news._NEWS_LIMIT == 5
    items = news.fetch_recent_news(JPM_TICKER)
    assert len(items) <= 5, f"expected <=5 news items, got {len(items)}"


def test_news_captures_summary() -> None:
    items = news.fetch_recent_news(JPM_TICKER)
    assert len(items) >= 1, "expected at least one news item for JPM"
    for item in items:
        assert "summary" in item, (
            f"news item missing 'summary' key: keys={list(item.keys())}"
        )
        assert isinstance(item["summary"], str)


def test_rendered_context_has_impact_ranked_section() -> None:
    ctx = build_company_context(JPM_TICKER)
    md = render_context_markdown(ctx, "company")
    assert "## Material events (SEC 8-K, impact-ranked" in md, (
        "missing impact-ranked Material events heading in render"
    )
    assert "TIER 1" in md, "missing TIER 1 label in rendered events"
    assert "## Recent market sentiment" in md, (
        "missing 'Recent market sentiment' section in render"
    )


def test_rendered_events_include_descriptions() -> None:
    ctx = build_company_context(JPM_TICKER)
    md = render_context_markdown(ctx, "company")
    descs = list(_8K_ITEM_DESCRIPTIONS.values())
    known_phrases = ["Officer", "officer", "departure", "Departure",
                     "acquisition", "bankruptcy", "accountant", "restatement"]
    found = any(phrase in md for phrase in known_phrases)
    assert found, (
        f"expected a known 5.02/4.02/2.01 description phrase in rendered output; "
        f"sampled descriptions: {descs[:5]}"
    )


def test_no_news_curator_or_digest() -> None:
    app_pipeline = REPO_ROOT / "app" / "pipeline"
    curator_path = app_pipeline / "news_curator.py"
    assert not curator_path.exists(), (
        f"unexpected file: {curator_path} (digest module was cancelled)"
    )

    news_py = (app_pipeline / "news.py").read_text(encoding="utf-8")
    digest_match = re.search(r"def\s+(digest|curate|summarise|summarize)\w*", news_py)
    assert digest_match is None, (
        f"news.py must not export a digest/curator function; found: "
        f"{digest_match.group(0) if digest_match else '?'}"
    )


def test_fetch_material_events_filters_non_8k_via_edgar() -> None:
    fake_submissions = {
        "filings": {
            "recent": {
                "form": ["10-K", "8-K", "10-Q", "8-K/A", "4", "8-K"],
                "accessionNumber": [
                    "0001-10K", "0001-8K1", "0001-10Q",
                    "0001-8KA", "0001-form4", "0001-8K2",
                ],
                "filingDate": [
                    "2026-01-01", "2026-02-01", "2026-03-01",
                    "2026-04-01", "2026-05-01", "2026-06-01",
                ],
                "primaryDocument": [
                    "a.htm", "b.htm", "c.htm", "d.htm", "e.htm", "f.htm",
                ],
                "items": ["", "5.02", "", "2.01,5.02", "", "7.01"],
            }
        }
    }
    with patch("app.pipeline.edgar.company_submissions", return_value=fake_submissions):
        events = fetch_material_events("0000789019", "MSFT")
    accs = [ev["accession"] for ev in events]
    assert "0001-10K" not in accs
    assert "0001-form4" not in accs
    by_acc = {ev["accession"]: ev for ev in events}
    assert by_acc["0001-8K1"]["tier"] == 1
    assert by_acc["0001-8KA"]["tier"] == 1
    assert by_acc["0001-8K2"]["tier"] == 3


def test_fetch_material_events_failure_returns_empty() -> None:
    with patch(
        "app.pipeline.edgar.company_submissions",
        side_effect=RuntimeError("sec down"),
    ):
        events = fetch_material_events("0000789019", "MSFT")
    assert events == []


def test_fetch_material_events_respects_window() -> None:
    fake_submissions = {
        "filings": {
            "recent": {
                "form": ["8-K", "8-K"],
                "accessionNumber": ["OLD-1", "NEW-1"],
                "filingDate": ["2020-01-15", "2026-06-01"],
                "primaryDocument": ["o.htm", "n.htm"],
                "items": ["5.02", "5.02"],
            }
        }
    }
    with patch("app.pipeline.edgar.company_submissions", return_value=fake_submissions):
        events = fetch_material_events("0000789019", "MSFT")
    accs = [ev["accession"] for ev in events]
    assert "OLD-1" not in accs, "5-year-old 8-K should be filtered out"
    assert "NEW-1" in accs


def test_rendered_news_section_label_is_sentiment() -> None:
    ctx = build_company_context(JPM_TICKER)
    md = render_context_markdown(ctx, "company")
    assert "## Recent market sentiment (yfinance, top 5)" in md, (
        "news section should be labelled 'Recent market sentiment (yfinance, top 5)'"
    )
