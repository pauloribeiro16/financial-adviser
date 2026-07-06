"""CLI entry: `python -m app.main --analysts buffett,burry --provider mock`.

Phase 3 — supports both legacy single-indicator runs and the new debate
pipeline. Dispatch rule:

    legacy mode  ←→  domain=macro AND exactly 1 analyst AND exactly 1
                     indicator AND no explicit ``--rounds > 1`` AND no
                     ``--no-synthesis``.
    debate mode  ←→  everything else (``--company``, multi-analyst, multi-
                     indicator, ``--rounds>1``, ``--interactive``, …).

S17 — every debate writes the full set of files by default:
``<TS>_<provider>_debate.md``, ``<TS>_<provider>_data.json``,
``<TS>_<provider>_summary.md``, ``<TS>_<provider>_meta.json``, and
``per_agent/<persona>.md`` for each analyst. The ``--format`` flag was
removed in S17 — there is no user choice anymore. ``--output PATH``
still bypasses the structure for scripting.
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
    ensure_parent_dir,
    render,
    render_debate_rich,
    render_per_agent,
    render_summary,
    run_dir,
    run_timestamp,
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
DEFAULT_OUTPUT_FORMAT = "debate"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Multi-persona macro / company assessment")
    subparsers = p.add_subparsers(dest="subcommand", required=False)

    watch = subparsers.add_parser(
        "watch",
        help="Refresh surveillance table for a sector (S14).",
        description="Run the S14 surveillance pipeline that aggregates "
                    "the latest per-ticker debates into a sector "
                    "watch-table under <output>/<sector>/<ticker>/current.md.",
    )
    watch.add_argument(
        "--sector", default=None,
        help="Sector name (e.g. Energy, Technology, Healthcare, Financial Services).",
    )
    watch.add_argument(
        "--ticker", default=None,
        help="Single ticker to refresh (requires --sector).",
    )
    watch.add_argument(
        "--all", dest="all_sectors", action="store_true",
        help="Refresh every known sector instead of one.",
    )
    watch.add_argument(
        "--provider", default="mock", choices=["mock", "minimax"],
        help="LLM provider (default: mock).",
    )
    watch.add_argument(
        "--output", default=None,
        help="Output root directory (default: ./out/surveillance).",
    )

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
    p.add_argument("--with-filings", action="store_true", default=False,
                   help="Download and summarize latest 10-K before debate (adds ~30s, ~$0.03).")
    p.add_argument("--env", default="development", choices=["development", "production"])
    p.add_argument(
        "--clean-mocks",
        action="store_true",
        help="Delete every file under out/mock/ (manual cleanup of mock outputs).",
    )
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

    S17 — there is no ``--format`` flag anymore; the default behavior is
    always "debate" mode with the full set of output files. Legacy mode is
    only entered for the trivial single-analyst/single-indicator macro case.
    """
    if args.interactive:
        return "debate", rounds if rounds is not None else 2, include_synthesis
    if domain == "company":
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


def _resolve_sector(target: str) -> str:
    try:
        from app.pipeline.market import quote as fetch_quote

        return fetch_quote(target).get("sector") or "unknown-sector"
    except Exception:
        return "unknown-sector"


def _write_meta_json(path: Path, meta: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(meta, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )


def _split_debate_per_persona(debate_md: str) -> dict[str, str]:
    """Split a rendered debate markdown on '### <persona>' headings.

    Returns ``{persona_id: section_markdown}``. The first ``# Debate`` heading
    (and any preamble up to the first ``### <persona>``) is dropped because
    per-agent files should be persona-scoped.
    """
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in debate_md.splitlines():
        if line.startswith("### "):
            current = line[4:].split()[0].strip()
            sections[current] = [line]
            continue
        if current is not None:
            sections[current].append(line)
    return {pid: "\n".join(lines).rstrip() + "\n" for pid, lines in sections.items()}


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
    run_ts = run_timestamp()
    completed_at = datetime.now().isoformat(timespec="seconds")
    indicator_id = indicators[0] if indicators else (get_target_indicators()[0] if get_target_indicators() else "UNKNOWN")
    meta = {
        "run_id": run_id,
        "run_ts": run_ts,
        "domain": "macro",
        "indicator": indicator_id,
        "analysts": analysts,
        "indicators": indicators or list(get_target_indicators()),
        "provider": args.provider,
        "target_date": target_date.isoformat(),
        "completed_at": completed_at,
        "n_assessments": len(results),
        "rounds": 1,
    }

    if args.output:
        out_path = Path(args.output)
        if out_path.suffix.lower() in {".md", ".txt"}:
            target = ensure_parent_dir(out_path)
            target.write_text(render(results, meta), encoding="utf-8")
            print(f"Written: {target}", file=sys.stderr)
        elif out_path.suffix.lower() == ".json":
            payload = {
                "run": meta,
                "assessments": [a.model_dump(mode="json") for a in results],
            }
            target = ensure_parent_dir(out_path)
            target.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
            print(f"Written: {target}", file=sys.stderr)
        else:
            run_dir_path = out_path
            run_dir_path.mkdir(parents=True, exist_ok=True)
            run_subdir = run_dir_path / f"{run_ts}_{args.provider}"
            run_subdir.mkdir(parents=True, exist_ok=True)
            _write_legacy_tree(run_subdir, results, meta, run_ts, args.provider)
            print(f"Written: {run_subdir}/  ({len(results)} assessments)", file=sys.stderr)
        return 0

    target_dir = run_dir("macro", indicator_id, indicator_id, args.provider)
    run_subdir = target_dir / f"{run_ts}_{args.provider}"
    run_subdir.mkdir(parents=True, exist_ok=True)
    _write_legacy_tree(run_subdir, results, meta, run_ts, args.provider)
    print(f"Written: {run_subdir}/  ({len(results)} assessments)", file=sys.stderr)
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
    if not args.session_id and targets:
        args.session_id = _auto_session_id(domain, targets[0])
        print(f"session_id: {args.session_id}", file=sys.stderr)

    if args.rich and args.output is None and sys.stdout.isatty():
        try:
            results: list[DebateResult] = []
            for tgt in targets:
                ctx = None
                if args.with_filings and domain == "company":
                    from app.pipeline.context import build_company_context

                    ctx = build_company_context(tgt, with_filings=True)
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
                        output_format=DEFAULT_OUTPUT_FORMAT,
                        ctx=ctx,
                    )
                )
        except RuntimeError as e:
            _print_error_provider(e)
            return 2
        except (ValueError, KeyError) as e:
            print(f"\nERROR: {e}", file=sys.stderr)
            return 2
        for r in results:
            render_debate_rich(r)
        print(f"\nDone: {len(results)} debates.", file=sys.stderr)
        return 0

    written_paths: list[Path] = []
    try:
        for tgt in targets:
            run_ts = run_timestamp()
            completed_at = datetime.now().isoformat(timespec="seconds")
            ctx = None
            if args.with_filings and domain == "company":
                from app.pipeline.context import build_company_context

                ctx = build_company_context(tgt, with_filings=True)
            result = run_debate_only(
                analysts=analysts,
                target=tgt,
                domain=domain,
                target_date=target_date,
                rounds=rounds,
                provider_name=args.provider,
                include_synthesis=include_synthesis,
                session_id=args.session_id,
                output_format=DEFAULT_OUTPUT_FORMAT,
                ctx=ctx,
            )

            if domain == "company":
                sector = _resolve_sector(tgt)
            else:
                sector = "macro"

            meta: dict[str, Any] = {
                "run_id": result.run_id,
                "run_ts": run_ts,
                "domain": domain,
                "target": tgt,
                "target_date": target_date.isoformat(),
                "analysts": analysts,
                "provider": args.provider,
                "rounds": rounds,
                "include_synthesis": include_synthesis,
                "completed_at": completed_at,
            }
            if domain == "company":
                meta["sector"] = sector
            else:
                meta["indicator"] = tgt

            target_group = sector if domain == "company" else tgt

            if args.output:
                out_path = Path(args.output)
                if out_path.suffix.lower() in {".md", ".txt"}:
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_text(_render_debate_md(result), encoding="utf-8")
                    written_paths.append(out_path)
                    print(f"Written: {out_path}", file=sys.stderr)
                elif out_path.suffix.lower() == ".json":
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    payload = {
                        "run": meta,
                        "debates": [result.model_dump(mode="json")],
                    }
                    out_path.write_text(
                        json.dumps(payload, indent=2, default=str), encoding="utf-8"
                    )
                    written_paths.append(out_path)
                    print(f"Written: {out_path}", file=sys.stderr)
                else:
                    run_dir_path = out_path / tgt
                    run_dir_path.mkdir(parents=True, exist_ok=True)
                    run_subdir = run_dir_path / f"{run_ts}_{args.provider}"
                    run_subdir.mkdir(parents=True, exist_ok=True)
                    _write_debate_tree(run_subdir, result, meta, run_ts, args.provider)
                    written_paths.append(run_subdir)
                    print(f"Written: {run_subdir}/  (1 debate)", file=sys.stderr)
                continue

            target_dir = run_dir(domain, target_group, tgt, args.provider)
            run_subdir = target_dir / f"{run_ts}_{args.provider}"
            run_subdir.mkdir(parents=True, exist_ok=True)
            _write_debate_tree(run_subdir, result, meta, run_ts, args.provider)
            written_paths.append(run_subdir)
            print(f"Written: {run_subdir}/  (1 debate)", file=sys.stderr)
            if args.provider != "mock":
                _auto_commit_and_push(run_ts, tgt, args.provider, run_subdir)
    except RuntimeError as e:
        _print_error_provider(e)
        return 2
    except (ValueError, KeyError) as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        return 2

    print(f"\nDone: {len(written_paths)} debates.", file=sys.stderr)
    return 0


def _auto_session_id(domain: str, target: str) -> str:
    return f"debate-{domain}-{target}-{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def _capture_rich_text(result: DebateResult) -> str:
    from io import StringIO

    from rich.console import Console

    buf = StringIO()
    con = Console(file=buf, force_terminal=False, color_system=None, width=120)
    render_debate_rich(result, console=con)
    return buf.getvalue()


def _render_debate_summary(result: DebateResult, meta: dict[str, Any], completed_at: str) -> str:
    lines: list[str] = [f"# Debate summary — {completed_at}", ""]
    for k, v in meta.items():
        if isinstance(v, list):
            lines.append(f"- **{k}:** {', '.join(map(str, v))}")
        else:
            lines.append(f"- **{k}:** {v}")
    lines.append("")
    return "\n".join(lines)


def _write_debate_tree(
    out_dir: Path,
    result: DebateResult,
    meta: dict[str, Any],
    run_ts: str,
    provider: str,
) -> None:
    debate_md = _render_debate_md(result)
    completed_at = meta.get("completed_at") or datetime.now().isoformat(timespec="seconds")
    summary_md = _render_debate_summary(result, meta, completed_at)
    (out_dir / f"{run_ts}_{provider}_debate.md").write_text(debate_md, encoding="utf-8")
    (out_dir / f"{run_ts}_{provider}_summary.md").write_text(summary_md, encoding="utf-8")
    payload = {
        "run": meta,
        "debates": [result.model_dump(mode="json")],
    }
    (out_dir / f"{run_ts}_{provider}_data.json").write_text(
        json.dumps(payload, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )
    pa_dir = out_dir / "per_agent"
    pa_dir.mkdir(parents=True, exist_ok=True)
    sections = _split_debate_per_persona(debate_md)
    for persona_id, sec_md in sections.items():
        (pa_dir / f"{persona_id}.md").write_text(sec_md, encoding="utf-8")
    _write_meta_json(out_dir / f"{run_ts}_{provider}_meta.json", meta)


def _write_legacy_tree(
    out_dir: Path,
    results: list[Any],
    meta: dict[str, Any],
    run_ts: str,
    provider: str,
) -> None:
    """Write the full legacy-mode file set into ``out_dir`` (a per-run subdir).

    Mirrors :func:`_write_debate_tree` for the Assessment-based legacy path.
    Files produced:
        - ``<TS>_<provider>_assessment.md``
        - ``<TS>_<provider>_data.json``
        - ``<TS>_<provider>_summary.md``
        - ``<TS>_<provider>_meta.json``
        - ``per_agent/<persona>_<indicator>.md`` per (persona, indicator) pair
    """
    assessment_md = render(results, meta)
    (out_dir / f"{run_ts}_{provider}_assessment.md").write_text(
        assessment_md, encoding="utf-8"
    )
    summary_md = render_summary(results, meta)
    (out_dir / f"{run_ts}_{provider}_summary.md").write_text(
        summary_md, encoding="utf-8"
    )
    payload = {
        "run": meta,
        "assessments": [a.model_dump(mode="json") for a in results],
    }
    (out_dir / f"{run_ts}_{provider}_data.json").write_text(
        json.dumps(payload, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )
    pa_dir = out_dir / "per_agent"
    pa_dir.mkdir(parents=True, exist_ok=True)
    per_agent = render_per_agent(results, meta)
    for persona_id, items in per_agent.items():
        for ind_id, md_content in items:
            (pa_dir / f"{persona_id}_{ind_id}.md").write_text(
                md_content, encoding="utf-8"
            )
    _write_meta_json(out_dir / f"{run_ts}_{provider}_meta.json", meta)


def _clean_mocks() -> int:
    """Delete every file under ``out/mock/`` and report the count."""
    import shutil

    mock_root = Path("out") / "mock"
    if not mock_root.exists():
        print(
            f"No mock directory to clean ({mock_root} does not exist).",
            file=sys.stderr,
        )
        return 0
    count = sum(1 for p in mock_root.rglob("*") if p.is_file())
    shutil.rmtree(mock_root)
    print(f"Removed {count} mock files from {mock_root}.", file=sys.stderr)
    return 0


def _auto_commit_and_push(run_ts: str, target: str, provider: str, run_dir: Path) -> None:
    """Auto-commit and push a real-provider analysis to origin/master.

    Skips silently on any error so the debate run is never blocked by git
    failures. Logs warnings on failure.
    """
    import subprocess

    from app.logging import get_logger

    log = get_logger(__name__)
    try:
        rel_path = run_dir.relative_to(Path.cwd())
    except ValueError:
        rel_path = run_dir
    try:
        subprocess.run(
            ["git", "add", str(rel_path)],
            check=True, capture_output=True, timeout=10,
        )
        diff_r = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            check=True, capture_output=True, timeout=5, text=True,
        )
        if not diff_r.stdout.strip():
            log.info("auto_commit.nothing_to_commit", target=target, provider=provider)
            return
        subprocess.run(
            ["git", "commit", "-m", f"analysis: {run_ts} {target} {provider}"],
            check=True, capture_output=True, timeout=15,
        )
        subprocess.run(
            ["git", "push", "origin", "master"],
            check=True, capture_output=True, timeout=30,
        )
        log.info("auto_commit.pushed", target=target, provider=provider, run_ts=run_ts)
    except subprocess.CalledProcessError as e:
        log.warning(
            "auto_commit.failed",
            target=target,
            provider=provider,
            error=str(e)[:200],
            stderr=e.stderr.decode()[:200] if e.stderr else "",
        )
    except subprocess.TimeoutExpired as e:
        log.warning("auto_commit.timeout", target=target, provider=provider, error=str(e))
    except FileNotFoundError:
        log.warning("auto_commit.git_not_found")


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
        "rounds": int(picked["rounds"]),
        "include_synthesis": bool(picked["include_synthesis"]),
        "analysts": [str(a) for a in picked["analysts"]],
        "with_filings": bool(picked.get("with_filings", False)),
    }


def _apply_pick(args: argparse.Namespace, picked: dict[str, Any]) -> None:
    """Mutate ``args`` and return the new (domain, target, indicators, analysts)."""
    args.provider = picked["provider"]
    args.rounds = picked["rounds"]
    args.no_synthesis = not picked["include_synthesis"]
    if getattr(args, "with_filings", None) is not True:
        args.with_filings = bool(picked.get("with_filings", False))


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if HAS_DOTENV and not os.getenv("FA_SKIP_DOTENV"):
        load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env", override=False)
    os.environ["MFL_ENV"] = args.env
    setup_logging(service="mi")

    if args.clean_mocks:
        return _clean_mocks()

    if getattr(args, "subcommand", None) == "watch":
        from app.watch.cli import cmd_watch as _cmd_watch

        output_value = getattr(args, "output", None)
        output_root = (
            Path(output_value) if output_value else Path("./out/surveillance")
        )
        rc = _cmd_watch(
            sector=getattr(args, "sector", None),
            ticker=getattr(args, "ticker", None),
            all_sectors=getattr(args, "all_sectors", False),
            provider=getattr(args, "provider", "mock"),
            output=output_root,
        )
        return rc

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
    company_targets: list[str] = []

    if args.company is not None:
        domain = "company"
        company_targets = [t.strip().upper() for t in args.company.split(",") if t.strip()]
        target = company_targets[0] if company_targets else None
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
        if picked.get("mode") == "watch":
            from app.watch.cli import cmd_watch as _cmd_watch

            output_root = Path(
                picked.get("output")
                or getattr(args, "output", None)
                or "./out/surveillance"
            )
            ticker = picked.get("target") if picked.get("single_ticker") else None
            return _cmd_watch(
                sector=picked.get("sector"),
                ticker=ticker,
                all_sectors=picked.get("all_sectors", False),
                provider=picked.get("provider", "mock"),
                output=output_root,
            )
    elif domain is None:
        legacy_analysts = _resolve_analysts(args, analysts_default)
        legacy_compatible = (
            not args.no_synthesis
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
        targets = company_targets if company_targets else [target or "AAPL"]

    return _run_debate(args, analysts, domain, targets, target_date, rounds_eff, synth_eff)


if __name__ == "__main__":
    raise SystemExit(main())
