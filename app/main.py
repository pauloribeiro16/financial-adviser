"""CLI entry: `python -m app.main --analysts buffett,burry --provider mock`.

Phase 3 — supports both legacy single-indicator runs and the new debate
pipeline. Dispatch rule:

    legacy mode  ←→  domain=macro AND exactly 1 analyst AND exactly 1
                     indicator AND no explicit ``--rounds > 1`` AND no
                     ``--no-synthesis`` AND ``--format`` in {md,json,per-agent}.
    debate mode  ←→  everything else (``--company``, multi-analyst, multi-
                     indicator, ``--rounds>1``, ``--format debate``,
                     ``--interactive``, …).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

from app.catalog import get_target_indicators
from app.cli_menu import (
    DEFAULT_COMPANY_ANALYSTS,
    DEFAULT_INDICATORS,
    DEFAULT_MACRO_ANALYSTS,
    interactive_pick,
)
from app.formatter import (
    default_output_path,
    default_run_dir,
    ensure_parent_dir,
    render,
    render_debate_rich,
    render_per_agent,
    render_summary,
)
from app.logging import setup_logging
from app.models import DebateResult, Direction
from app.runner import run, run_debate_only

try:
    from dotenv import load_dotenv

    HAS_DOTENV = True
except ImportError:
    HAS_DOTENV = False

DEFAULT_INDICATOR = "US.UST10Y"
LEGACY_FORMATS = {"md", "json", "per-agent"}


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Multi-persona macro / company assessment")
    p.add_argument("--analysts", default=None,
                   help="Comma-separated persona IDs (overrides --analysts-default / --analysts-all)")
    p.add_argument("--analysts-all", action="store_true",
                   help="Use every persona in ALL_AGENTS (15).")
    p.add_argument("--analysts-default", action="store_true",
                   help="Use the domain default personas (company: buffett,lynch,burry,taleb; "
                        "macro: dalio,gundlach,volcker,greenspan).")
    p.add_argument("--company", default=None,
                   help="Company mode: ticker symbol (e.g. AAPL). Mutually exclusive with --indicators.")
    p.add_argument("--indicators", default=None,
                   help="Comma-separated indicator IDs (default: single US.UST10Y in legacy mode).")
    p.add_argument("--provider", default="mock", choices=["mock", "minimax"],
                   help="LLM provider: 'mock' (offline) or 'minimax' (real Anthropic-compatible). Default: mock.")
    p.add_argument("--date", default=None,
                   help="Target date YYYY-MM-DD (default: today)")
    p.add_argument("--target-date", dest="target_date", default=None,
                   help="Alias for --date")
    p.add_argument("--format", default="debate", choices=["md", "json", "per-agent", "debate"],
                   help="Output format (default: debate). Legacy formats (md/json/per-agent) "
                        "trigger the legacy runner when conditions match.")
    p.add_argument("--output", default=None,
                   help="Write output to file/dir (legacy: per-agent→./out/run_<TS>/, md→./out/run_<TS>.md, "
                        "json→stdout; debate→./out/debate_<TS>/ or --output PATH).")
    p.add_argument("--rounds", type=int, default=None,
                   help="Number of debate rounds (default: 2). Forces debate mode when > 1.")
    p.add_argument("--no-synthesis", action="store_true",
                   help="Skip the moderator synthesis step. Forces debate mode.")
    p.add_argument("--interactive", action="store_true",
                   help="Force the interactive questionary menu even when flags are provided.")
    p.add_argument("--session-id", dest="session_id", default=None,
                   help="Langfuse session_id for grouping debate spans under one trace.")
    p.add_argument("--rich", action="store_true",
                   help="In debate mode with no --output and a TTY stdout, render the result "
                        "via rich tables/colors instead of writing Markdown.")
    p.add_argument("--env", default="development", choices=["development", "production"])
    return p.parse_args(argv)


def _resolve_analysts(args: argparse.Namespace, default: list[str]) -> list[str]:
    if args.analysts_all:
        from app.agents import ALL_AGENTS

        return sorted(ALL_AGENTS)
    if args.analysts:
        return [a.strip() for a in args.analysts.split(",") if a.strip()]
    if args.analysts_default:
        return list(default)
    return list(default)


def _resolve_target_date(args: argparse.Namespace) -> date:
    raw = args.date or args.target_date
    if raw:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    return date.today()


def _decide_mode(
    args: argparse.Namespace,
    domain: str | None,
    indicators: list[str] | None,
    analysts: list[str],
    rounds: int,
    include_synthesis: bool,
) -> tuple[str, int, bool]:
    """Return (mode, rounds_effective, include_synthesis_effective).

    ``mode`` is either ``"legacy"`` or ``"debate"``. ``rounds_effective`` is
    the rounds count to actually use (legacy always treats rounds as 1).
    """
    if args.interactive:
        return "debate", rounds if rounds is not None else 2, include_synthesis
    if domain == "company":
        return "debate", rounds if rounds is not None else 2, include_synthesis
    if args.format == "debate":
        return "debate", rounds if rounds is not None else 2, include_synthesis
    if not include_synthesis:
        return "debate", rounds if rounds is not None else 2, include_synthesis
    if rounds is not None and rounds > 1:
        return "debate", rounds, include_synthesis
    if len(analysts) > 1:
        return "debate", rounds if rounds is not None else 2, include_synthesis
    if indicators is not None and len(indicators) > 1:
        return "debate", rounds if rounds is not None else 2, include_synthesis
    if domain == "macro":
        return "legacy", 1, True
    return "debate", rounds if rounds is not None else 2, include_synthesis


def _render_debate_md(result: DebateResult) -> str:
    lines: list[str] = [
        f"# Debate — {result.target} ({result.domain.value}) — {result.target_date}",
        "",
        f"> Provider: `{result.provider}` · Analysts: {', '.join(result.analysts)} · "
        f"Rounds: {1 + len({rb.round for rb in result.rebuttals})}",
        "",
    ]
    if not result.theses:
        lines.append("_(no theses)_")
        return "\n".join(lines) + "\n"

    theses_by_round: dict[int, list[Any]] = {}
    for t in result.theses:
        theses_by_round.setdefault(t.round, []).append(t)
    for rb in result.rebuttals:
        theses_by_round.setdefault(rb.round, []).append(rb)

    for round_idx in sorted(theses_by_round):
        bucket = theses_by_round[round_idx]
        if round_idx == 0:
            section_title = "Round 0 — Initial theses"
        else:
            section_title = f"Round {round_idx} — Rebuttals"
        lines.append(f"## {section_title}")
        lines.append("")
        for item in bucket:
            if hasattr(item, "verdict"):
                verdict = item.verdict.value if isinstance(item.verdict, Direction) else str(item.verdict)
                lines.append(f"### {item.agent_id}")
                lines.append("")
                lines.append(f"- **Verdict:** {verdict} (conviction {item.conviction:.2f})")
                if item.key_drivers:
                    lines.append("- **Key drivers:**")
                    for d in item.key_drivers:
                        lines.append(f"  - {d}")
                lines.append("")
                lines.append("**Reasoning:**")
                lines.append("")
                lines.append(item.reasoning or "_(empty)_")
                lines.append("")
            else:
                verdict = (
                    item.revised_verdict.value
                    if isinstance(item.revised_verdict, Direction)
                    else str(item.revised_verdict)
                )
                lines.append(f"### {item.agent_id} → {', '.join(item.targets) or '(none)'}")
                lines.append("")
                lines.append(f"- **Revised verdict:** {verdict} (conviction {item.revised_conviction:.2f})")
                if item.concessions:
                    lines.append(f"- **Concessions:** {'; '.join(item.concessions)}")
                if item.disagreements:
                    lines.append(f"- **Disagreements:** {'; '.join(item.disagreements)}")
                lines.append("")
                lines.append("**Reasoning:**")
                lines.append("")
                lines.append(item.reasoning or "_(empty)_")
                lines.append("")

    if result.verdict is not None:
        v = result.verdict
        lines.append("## Synthesis")
        lines.append("")
        lines.append(f"- **Consensus:** {v.consensus.value}")
        lines.append(f"- **Final call:** {v.final_call}")
        lines.append(f"- **Confidence:** {v.confidence:.2f}")
        lines.append(f"- **Avg conviction:** {v.avg_conviction:.2f}")
        lines.append(f"- **Tally:** bull={v.bull_count} · bear={v.bear_count} · neutral={v.neutral_count}")
        if v.points_of_agreement:
            lines.append("")
            lines.append("### Points of agreement")
            for p in v.points_of_agreement:
                lines.append(f"- {p}")
        if v.points_of_disagreement:
            lines.append("")
            lines.append("### Points of disagreement")
            for p in v.points_of_disagreement:
                lines.append(f"- {p}")
        lines.append("")
        lines.append("### Summary")
        lines.append("")
        lines.append(v.summary or "_(empty)_")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _print_error_provider(e: RuntimeError) -> None:
    print(f"\nERROR: {e}", file=sys.stderr)
    print("Hint: the LLM provider rejected the call (probably a 401-style auth error).", file=sys.stderr)
    print("      - If using --provider minimax, make sure MINIMAX_API_KEY is set (env var or .env).", file=sys.stderr)
    print("      - For offline runs, omit --provider (defaults to mock) or pass --provider mock.", file=sys.stderr)


def _run_legacy(
    args: argparse.Namespace,
    analysts: list[str],
    indicators: list[str],
    target_date: date,
) -> int:
    try:
        results = run(
            analysts=analysts,
            indicators=indicators,
            target_date=target_date,
            provider_name=args.provider,
        )
    except RuntimeError as e:
        _print_error_provider(e)
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


def _run_debate(
    args: argparse.Namespace,
    analysts: list[str],
    domain: str,
    targets: list[str],
    target_date: date,
    rounds: int,
    include_synthesis: bool,
) -> int:
    try:
        results: list[DebateResult] = []
        for tgt in targets:
            results.append(
                run_debate_only(
                    analysts=analysts,
                    target=tgt,
                    domain=domain,
                    target_date=target_date,
                    rounds=rounds,
                    provider_name=args.provider,
                    include_synthesis=include_synthesis,
                    session_id=args.session_id,
                )
            )
    except RuntimeError as e:
        _print_error_provider(e)
        return 2
    except (ValueError, KeyError) as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        return 2

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    completed_at = datetime.now().isoformat(timespec="seconds")
    meta = {
        "run_id": run_id,
        "domain": domain,
        "targets": [r.target for r in results],
        "analysts": analysts,
        "rounds": rounds,
        "include_synthesis": include_synthesis,
        "provider": args.provider,
        "target_date": target_date.isoformat(),
        "completed_at": completed_at,
        "n_debates": len(results),
    }

    if args.format == "json":
        payload = {
            "run": meta,
            "debates": [r.model_dump(mode="json") for r in results],
        }
        text = json.dumps(payload, indent=2, default=str)
        if args.output:
            Path(args.output).write_text(text, encoding="utf-8")
            print(f"Written: {args.output}", file=sys.stderr)
        else:
            print(text)
        print(f"\nDone: {len(results)} debates.", file=sys.stderr)
        return 0

    if args.rich and args.output is None and sys.stdout.isatty():
        for r in results:
            render_debate_rich(r)
        print(f"\nDone: {len(results)} debates.", file=sys.stderr)
        return 0

    if args.output:
        out_path = Path(args.output)
        if out_path.suffix.lower() in {".md", ".txt"}:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            parts = [_render_debate_md(r) for r in results]
            out_path.write_text("\n---\n\n".join(parts), encoding="utf-8")
            print(f"Written: {out_path}", file=sys.stderr)
        elif out_path.suffix.lower() == ".json":
            payload = {
                "run": meta,
                "debates": [r.model_dump(mode="json") for r in results],
            }
            out_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
            print(f"Written: {out_path}", file=sys.stderr)
        else:
            run_dir_path = out_path
            run_dir_path.mkdir(parents=True, exist_ok=True)
            for r in results:
                (run_dir_path / f"{r.target}.md").write_text(_render_debate_md(r), encoding="utf-8")
            summary_lines = [f"# Debate summary — {completed_at}", ""]
            for k, v in meta.items():
                if isinstance(v, list):
                    summary_lines.append(f"- **{k}:** {', '.join(map(str, v))}")
                else:
                    summary_lines.append(f"- **{k}:** {v}")
            (run_dir_path / "_summary.md").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
            print(f"Written: {run_dir_path}/  ({len(results)} debates)", file=sys.stderr)
    else:
        run_dir_path = Path(default_run_dir(run_id=run_id).replace("run_", "debate_"))
        run_dir_path.mkdir(parents=True, exist_ok=True)
        for r in results:
            (run_dir_path / f"{r.target}.md").write_text(_render_debate_md(r), encoding="utf-8")
        summary_lines = [f"# Debate summary — {completed_at}", ""]
        for k, v in meta.items():
            if isinstance(v, list):
                summary_lines.append(f"- **{k}:** {', '.join(map(str, v))}")
            else:
                summary_lines.append(f"- **{k}:** {v}")
        (run_dir_path / "_summary.md").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
        print(f"Written: {run_dir_path}/  ({len(results)} debates)", file=sys.stderr)

    print(f"\nDone: {len(results)} debates.", file=sys.stderr)
    return 0


def _interactive_pick(
    args: argparse.Namespace,
    domain: str | None,
    target: str | None,
    indicators: list[str] | None,
    analysts_default: list[str],
) -> dict[str, Any] | None:
    """Run the interactive menu; return the picked dict or ``None`` if cancelled."""
    defaults: dict[str, Any] = {
        "domain": domain or "macro",
        "target": target or DEFAULT_INDICATOR,
        "indicators": indicators or list(DEFAULT_INDICATORS),
        "provider": args.provider,
        "analysts": _resolve_analysts(args, analysts_default),
        "rounds": args.rounds if args.rounds is not None else 2,
        "format": args.format,
        "include_synthesis": not args.no_synthesis,
    }
    try:
        picked = interactive_pick(defaults)
    except KeyboardInterrupt:
        print("Interactive menu cancelled.", file=sys.stderr)
        return None
    return {
        "domain": str(picked["domain"]),
        "target": str(picked["target"]),
        "indicators": list(picked.get("indicators") or []),
        "provider": str(picked["provider"]),
        "format": str(picked["format"]),
        "rounds": int(picked["rounds"]),
        "include_synthesis": bool(picked["include_synthesis"]),
        "analysts": [str(a) for a in picked["analysts"]],
    }


def _apply_pick(args: argparse.Namespace, picked: dict[str, Any]) -> None:
    """Mutate ``args`` and return the new (domain, target, indicators, analysts)."""
    args.provider = picked["provider"]
    args.format = picked["format"]
    args.rounds = picked["rounds"]
    args.no_synthesis = not picked["include_synthesis"]


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
    if args.company is not None and args.indicators is not None:
        print("ERROR: --company and --indicators are mutually exclusive.", file=sys.stderr)
        return 2

    indicators: list[str] | None = None
    domain: str | None
    target: str | None = None

    if args.company is not None:
        domain = "company"
        target = args.company.strip().upper()
        analysts_default = DEFAULT_COMPANY_ANALYSTS
    elif args.indicators is not None:
        domain = "macro"
        indicators = [i.strip() for i in args.indicators.split(",") if i.strip()]
        target = indicators[0] if indicators else None
        analysts_default = DEFAULT_MACRO_ANALYSTS
    else:
        domain = None
        target = None
        indicators = None
        analysts_default = DEFAULT_MACRO_ANALYSTS

    picked: dict[str, Any] | None = None
    if args.interactive:
        picked = _interactive_pick(args, domain, target, indicators, analysts_default)
        if picked is None:
            return 130
    elif domain is None:
        legacy_analysts = _resolve_analysts(args, analysts_default)
        legacy_compatible = (
            args.format in LEGACY_FORMATS
            and not args.no_synthesis
            and args.rounds is None
            and not args.analysts_all
            and len(legacy_analysts) == 1
        )
        if legacy_compatible:
            target_date = _resolve_target_date(args)
            return _run_legacy(args, legacy_analysts, [DEFAULT_INDICATOR], target_date)
        picked = _interactive_pick(args, domain, target, indicators, analysts_default)
        if picked is None:
            return 130

    if picked is not None:
        domain = picked["domain"]
        target = picked["target"]
        indicators = list(picked["indicators"]) or None
        _apply_pick(args, picked)
        analysts_default = (
            DEFAULT_COMPANY_ANALYSTS if domain == "company" else DEFAULT_MACRO_ANALYSTS
        )
        analysts = list(picked["analysts"])
    else:
        analysts = _resolve_analysts(args, analysts_default)

    target_date = _resolve_target_date(args)
    include_synthesis = not args.no_synthesis

    rounds_for_mode = args.rounds
    mode, rounds_eff, synth_eff = _decide_mode(
        args, domain, indicators, analysts, rounds_for_mode, include_synthesis
    )

    if mode == "legacy":
        legacy_indicators = indicators if indicators else [DEFAULT_INDICATOR]
        return _run_legacy(args, analysts, legacy_indicators, target_date)

    if domain == "macro":
        targets = indicators if indicators else [DEFAULT_INDICATOR]
    else:
        targets = [target or "AAPL"]

    return _run_debate(args, analysts, domain, targets, target_date, rounds_eff, synth_eff)


if __name__ == "__main__":
    raise SystemExit(main())
