from __future__ import annotations

import json
from pathlib import Path

from app.watch.reference_reader import load_latest_debate


def _make_debate(
    ticker_dir: Path,
    ts: str,
    micro: str,
    provider: str,
    *,
    with_meta: bool = True,
) -> tuple[Path, Path]:
    name = f"{ts}_{micro}_{provider}"
    debate = ticker_dir / f"{name}_debate.md"
    meta = ticker_dir / f"{name}_meta.json"
    debate.write_text(f"# Debate {name}\n", encoding="utf-8")
    if with_meta:
        meta.write_text(
            json.dumps({"ticker": ticker_dir.name, "sector": ticker_dir.parent.name,
                        "provider": provider, "run_ts": f"{ts}_{micro}"}),
            encoding="utf-8",
        )
    return debate, meta


def test_empty_sector_dir_returns_none(tmp_path: Path) -> None:
    base = tmp_path / "out" / "company"
    (base / "Energy" / "XOM").mkdir(parents=True)
    assert load_latest_debate("Energy", "XOM", base=base) is None


def test_missing_sector_returns_none(tmp_path: Path) -> None:
    base = tmp_path / "out" / "company"
    (base / "Energy").mkdir(parents=True)
    assert load_latest_debate("NonExistent", "XOM", base=base) is None


def test_single_debate_returned(tmp_path: Path) -> None:
    base = tmp_path / "out" / "company"
    ticker_dir = base / "Energy" / "XOM"
    ticker_dir.mkdir(parents=True)
    debate, meta = _make_debate(ticker_dir, "2026-07-03T12-00-00", "000", "mock")

    ref = load_latest_debate("Energy", "XOM", base=base)

    assert ref is not None
    assert ref.debate_path == debate
    assert ref.meta_path == meta
    assert ref.ticker == "XOM"
    assert ref.sector == "Energy"
    assert ref.meta["provider"] == "mock"


def test_multiple_debates_returns_latest_by_ts(tmp_path: Path) -> None:
    base = tmp_path / "out" / "company"
    ticker_dir = base / "Energy" / "XOM"
    ticker_dir.mkdir(parents=True)
    _make_debate(ticker_dir, "2026-07-03T12-00-00", "000", "mock")
    later, _ = _make_debate(ticker_dir, "2026-07-04T12-00-00", "000", "mock")
    _make_debate(ticker_dir, "2026-07-03T18-00-00", "000", "mock")

    ref = load_latest_debate("Energy", "XOM", base=base)

    assert ref is not None
    assert ref.debate_path == later


def test_meta_loaded_from_sibling(tmp_path: Path) -> None:
    base = tmp_path / "out" / "company"
    ticker_dir = base / "Energy" / "XOM"
    ticker_dir.mkdir(parents=True)
    debate, meta = _make_debate(ticker_dir, "2026-07-03T12-00-00", "000", "minimax")

    ref = load_latest_debate("Energy", "XOM", base=base)

    assert ref is not None
    assert ref.meta_path == meta
    assert ref.meta["provider"] == "minimax"


def test_meta_absent_yields_empty_meta(tmp_path: Path) -> None:
    base = tmp_path / "out" / "company"
    ticker_dir = base / "Energy" / "XOM"
    ticker_dir.mkdir(parents=True)
    debate, _ = _make_debate(ticker_dir, "2026-07-03T12-00-00", "000", "mock", with_meta=False)

    ref = load_latest_debate("Energy", "XOM", base=base)

    assert ref is not None
    assert ref.debate_path == debate
    assert ref.meta_path is None
    assert ref.meta == {}


def test_latest_falls_back_to_mtime_when_no_parseable_ts(tmp_path: Path) -> None:
    base = tmp_path / "out" / "company"
    ticker_dir = base / "Energy" / "XOM"
    ticker_dir.mkdir(parents=True)

    import os
    older = ticker_dir / "manual_old_debate.md"
    older.write_text("# old", encoding="utf-8")
    newer = ticker_dir / "manual_new_debate.md"
    newer.write_text("# new", encoding="utf-8")
    older_mtime = ticker_dir.stat().st_mtime
    newer_mtime = older_mtime + 3600
    os.utime(older, (older_mtime, older_mtime))
    os.utime(newer, (newer_mtime, newer_mtime))

    ref = load_latest_debate("Energy", "XOM", base=base)

    assert ref is not None
    assert ref.debate_path == newer


def test_latest_uses_parseable_ts_over_unparseable(tmp_path: Path) -> None:
    base = tmp_path / "out" / "company"
    ticker_dir = base / "Energy" / "XOM"
    ticker_dir.mkdir(parents=True)

    import os
    weird = ticker_dir / "weird_debate.md"
    weird.write_text("# weird", encoding="utf-8")
    future_mtime = ticker_dir.stat().st_mtime + 3600
    os.utime(weird, (future_mtime, future_mtime))

    parseable, _ = _make_debate(ticker_dir, "2026-07-04T12-00-00", "000", "mock")

    ref = load_latest_debate("Energy", "XOM", base=base)

    assert ref is not None
    assert ref.debate_path == parseable
