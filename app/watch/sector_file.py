from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from app.logging import get_logger
from app.watch.markdown_renderer import render_sector_index

log = get_logger(__name__)


def write_sector_index(
    sector: str,
    entries: list[dict[str, Any]],
    output_root: Path,
) -> Path:
    sector_root = output_root / sector.lower().replace(" ", "-")
    sector_root.mkdir(parents=True, exist_ok=True)
    path = sector_root / "_index.md"
    path.write_text(render_sector_index(sector, entries), encoding="utf-8")
    log.info(
        "watch.sector_file.written",
        sector=sector,
        path=str(path),
        n_entries=len(entries),
    )
    return path


def append_history(
    sector: str,
    ticker: str,
    record: dict[str, Any],
    output_root: Path,
) -> Path:
    ticker_dir = output_root / sector.lower().replace(" ", "-") / ticker.upper()
    ticker_dir.mkdir(parents=True, exist_ok=True)
    path = ticker_dir / "history.json"
    history: list[dict[str, Any]] = []
    if path.exists():
        try:
            import json
            history = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(history, list):
                history = []
        except Exception:
            history = []
    record = dict(record)
    record.setdefault("ts", datetime.now().isoformat(timespec="seconds"))
    record.setdefault("ticker", ticker.upper())
    history.append(record)
    import json
    path.write_text(json.dumps(history, indent=2, default=str), encoding="utf-8")
    log.info("watch.sector_file.history_appended", ticker=ticker, path=str(path))
    return path


__all__ = ["write_sector_index", "append_history"]
