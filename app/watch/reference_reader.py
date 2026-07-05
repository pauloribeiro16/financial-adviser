from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.logging import get_logger

log = get_logger(__name__)

_DEBATE_SUFFIX = "_debate.md"
_META_SUFFIX = "_meta.json"
_TS_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}(?:_\d+)?)_(?P<provider>[^_]+)_debate\.md$"
)


class DebateRef(BaseModel):
    ticker: str
    sector: str
    debate_path: Path
    meta_path: Path | None
    meta: dict[str, Any] = Field(default_factory=dict)
    debate_mtime: float

    model_config = {"arbitrary_types_allowed": True}


def _parse_ts_key(name: str) -> tuple[str, int] | None:
    m = _TS_RE.match(name)
    if not m:
        return None
    return (m.group("ts"), m.start("provider"))


def _scan_debates(ticker_dir: Path) -> list[tuple[Path, float, tuple[str, int] | None]]:
    out: list[tuple[Path, float, tuple[str, int] | None]] = []
    for p in ticker_dir.glob(f"*{_DEBATE_SUFFIX}"):
        if not p.is_file():
            continue
        key = _parse_ts_key(p.name)
        out.append((p, p.stat().st_mtime, key))
    return out


def _pick_latest(
    candidates: list[tuple[Path, float, tuple[str, int] | None]],
) -> tuple[Path, float, tuple[str, int] | None]:
    keyed = [c for c in candidates if c[2] is not None]
    if keyed:
        keyed.sort(key=lambda c: c[2][0])
        return keyed[-1]
    candidates.sort(key=lambda c: c[1])
    return candidates[-1]


def _load_meta(meta_path: Path) -> dict[str, Any]:
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("watch.reference_reader.meta_unreadable", path=str(meta_path), error=str(e))
        return {}


def load_latest_debate(
    sector: str,
    ticker: str,
    base: Path = Path("./out/company"),
) -> DebateRef | None:
    ticker_dir = base / sector / ticker
    if not ticker_dir.is_dir():
        log.info(
            "watch.reference_reader.no_ticker_dir",
            sector=sector,
            ticker=ticker,
            path=str(ticker_dir),
        )
        return None

    candidates = _scan_debates(ticker_dir)
    if not candidates:
        log.info(
            "watch.reference_reader.no_debates",
            sector=sector,
            ticker=ticker,
            path=str(ticker_dir),
        )
        return None

    debate_path, mtime, _ = _pick_latest(candidates)
    meta_path = debate_path.with_name(debate_path.name.replace(_DEBATE_SUFFIX, _META_SUFFIX))
    meta: dict[str, Any] = {}
    if meta_path.exists():
        meta = _load_meta(meta_path)

    return DebateRef(
        ticker=ticker,
        sector=sector,
        debate_path=debate_path,
        meta_path=meta_path if meta_path.exists() else None,
        meta=meta,
        debate_mtime=mtime,
    )
