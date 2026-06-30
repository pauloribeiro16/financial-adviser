"""CLI entry: `python -m app.main --analysts buffett,burry --provider mock`."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

from app.catalog import get_target_indicators
from app.logging import setup_logging
from app.runner import run


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Multi-persona macro assessment")
    p.add_argument("--analysts", default="buffett,burry,greenspan,volcker,dimon",
                   help="Comma-separated persona IDs (default: buffett,burry,greenspan,volcker,dimon)")
    p.add_argument("--indicators", default=None,
                   help="Comma-separated indicator IDs (default: all 8 in catalog)")
    p.add_argument("--provider", default="minimax", choices=["minimax", "mock"])
    p.add_argument("--date", default=None,
                   help="Target date YYYY-MM-DD (default: today)")
    p.add_argument("--target-date", dest="target_date", default=None,
                   help="Alias for --date")
    p.add_argument("--output", default=None,
                   help="Write JSON to file (default: stdout)")
    p.add_argument("--env", default="development", choices=["development", "production"])
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    setup_logging(service="mi")
    import os
    os.environ["MFL_ENV"] = args.env

    analysts = [a.strip() for a in args.analysts.split(",") if a.strip()]
    indicators = [i.strip() for i in args.indicators.split(",")] if args.indicators else None
    target_date = (
        datetime.strptime(args.date, "%Y-%m-%d").date()
        if args.date
        else (datetime.strptime(args.target_date, "%Y-%m-%d").date() if args.target_date else date.today())
    )

    results = run(
        analysts=analysts,
        indicators=indicators,
        target_date=target_date,
        provider_name=args.provider,
    )

    payload = {
        "run": {
            "analysts": analysts,
            "indicators": indicators or list(get_target_indicators()),
            "provider": args.provider,
            "target_date": target_date.isoformat(),
            "completed_at": datetime.now().isoformat(timespec="seconds"),
        },
        "assessments": [a.model_dump(mode="json") for a in results],
    }

    text = json.dumps(payload, indent=2, default=str)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)

    print(f"\nDone: {len(results)} assessments.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
