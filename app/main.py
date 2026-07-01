"""CLI entry: `python -m app.main --analysts buffett,burry --provider mock`."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

from app.catalog import get_target_indicators
from app.formatter import (
    default_output_path,
    default_run_dir,
    ensure_parent_dir,
    render,
    render_per_agent,
    render_summary,
)
from app.logging import setup_logging
from app.runner import run

try:
    from dotenv import load_dotenv

    HAS_DOTENV = True
except ImportError:
    HAS_DOTENV = False

DEFAULT_INDICATOR = "US.UST10Y"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Multi-persona macro assessment")
    p.add_argument("--analysts", default="buffett,burry,greenspan,volcker,dimon",
                   help="Comma-separated persona IDs (default: buffett,burry,greenspan,volcker,dimon)")
    p.add_argument("--indicators", default=None,
                   help="Comma-separated indicator IDs (default: single US.UST10Y)")
    p.add_argument("--provider", default="mock", choices=["mock", "minimax"],
                   help="LLM provider: 'mock' (offline, no API key) or 'minimax' (real Anthropic-compatible API). Default: mock.")
    p.add_argument("--date", default=None,
                   help="Target date YYYY-MM-DD (default: today)")
    p.add_argument("--target-date", dest="target_date", default=None,
                   help="Alias for --date")
    p.add_argument("--format", default="per-agent", choices=["md", "json", "per-agent"],
                   help="Output format (default: per-agent)")
    p.add_argument("--output", default=None,
                   help="Write output to file/dir (default: per-agent → ./out/run_<TS>/, md → ./out/run_<TS>.md, json → stdout)")
    p.add_argument("--env", default="development", choices=["development", "production"])
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if HAS_DOTENV and not os.getenv("FA_SKIP_DOTENV"):
        load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env", override=False)
    os.environ["MFL_ENV"] = args.env
    setup_logging(service="mi")

    if args.indicators == "":
        print(
            "ERROR: --indicators cannot be empty. Pass at least one indicator id (e.g. 'US.FFR').",
            file=sys.stderr,
        )
        return 1

    analysts = [a.strip() for a in args.analysts.split(",") if a.strip()]
    indicators = (
        [i.strip() for i in args.indicators.split(",")]
        if args.indicators
        else [DEFAULT_INDICATOR]
    )
    target_date = (
        datetime.strptime(args.date, "%Y-%m-%d").date()
        if args.date
        else (datetime.strptime(args.target_date, "%Y-%m-%d").date() if args.target_date else date.today())
    )

    try:
        results = run(
            analysts=analysts,
            indicators=indicators,
            target_date=target_date,
            provider_name=args.provider,
        )
    except RuntimeError as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        print("Hint: you passed --provider minimax; either set MINIMAX_API_KEY in the environment, or drop --provider to use the offline 'mock' default.", file=sys.stderr)
        return 2

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    completed_at = datetime.now().isoformat(timespec="seconds")
    meta = {
        "run_id": run_id,
        "analysts": analysts,
        "indicators": indicators or list(get_target_indicators()),
        "provider": args.provider,
        "target_date": target_date.isoformat(),
        "completed_at": completed_at,
        "n_assessments": len(results),
    }

    if args.format == "per-agent":
        run_dir = args.output or default_run_dir(run_id=run_id)
        run_dir_path = Path(run_dir)
        run_dir_path.mkdir(parents=True, exist_ok=True)
        per_agent = render_per_agent(results, meta)
        for persona_id, items in per_agent.items():
            persona_dir = run_dir_path / persona_id
            persona_dir.mkdir(exist_ok=True)
            for indicator_id, md_content in items:
                (persona_dir / f"{indicator_id}.md").write_text(md_content, encoding="utf-8")
        summary = render_summary(results, meta)
        (run_dir_path / "_summary.md").write_text(summary, encoding="utf-8")
        print(f"Written: {run_dir}/  ({len(results)} assessments)", file=sys.stderr)
    elif args.format == "md":
        text = render(results, meta)
        output_path = args.output or default_output_path()
        target = ensure_parent_dir(output_path)
        target.write_text(text, encoding="utf-8")
        print(f"Written: {target}", file=sys.stderr)
    else:
        payload = {
            "run": meta,
            "assessments": [a.model_dump(mode="json") for a in results],
        }
        text = json.dumps(payload, indent=2, default=str)
        if args.output:
            Path(args.output).write_text(text, encoding="utf-8")
            print(f"Written: {args.output}", file=sys.stderr)
        else:
            print(text)

    print(f"\nDone: {len(results)} assessments.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
