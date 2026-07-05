from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from app.models import Assessment, DebateResult, Direction

__all__ = [
    "render",
    "render_per_agent",
    "render_summary",
    "render_debate_rich",
    "default_output_path",
    "default_run_dir",
    "ensure_parent_dir",
    "slugify",
    "run_timestamp",
    "output_root",
    "run_dir",
    "per_agent_dir",
    "output_path",
    "PERSONA_NAMES",
]

PERSONA_NAMES: dict[str, str] = {
    "buffett": "Warren E. Buffett",
    "lynch": "Peter Lynch",
    "dalio": "Ray Dalio",
    "burry": "Michael Burry",
    "greenspan": "Alan Greenspan",
    "bernanke": "Ben Bernanke",
    "volcker": "Paul Volcker",
    "dimon": "Jamie Dimon",
    "eisman": "Steve Eisman",
    "grantham": "Jeremy Grantham",
    "simons": "Jim Simons",
    "taleb": "Nassim Nicholas Taleb",
    "wood": "Cathie Wood",
    "gundlach": "Jeffrey Gundlach",
    "thaler": "Richard Thaler",
}

_EMPTY = "_(empty)_"


def _fmt(value: object) -> str:
    if value is None:
        return _EMPTY
    s = str(value).strip()
    return s if s else _EMPTY


def _meta_lines(meta: dict) -> list[str]:
    keys = (
        ("Target date", "target_date"),
        ("Provider", "provider"),
        ("Analysts", "analysts"),
        ("Indicators", "indicators"),
        ("Completed at", "completed_at"),
        ("Total assessments", "n_assessments"),
    )
    lines: list[str] = []
    for label, key in keys:
        if key not in meta:
            continue
        raw = meta[key]
        if isinstance(raw, list):
            value = ", ".join(str(x) for x in raw) if raw else _EMPTY
        else:
            value = _fmt(raw)
        lines.append(f"- **{label}:** {value}")
    return lines


def _summary_rows(assessments: list[Assessment]) -> list[str]:
    rows = [
        "| Analyst | Indicator | Signal | Strength |",
        "|---|---|---|---|",
    ]
    for a in assessments:
        analyst = PERSONA_NAMES.get(a.agent_id, a.agent_id)
        rows.append(
            f"| {analyst} (`{a.agent_id}`) | `{a.indicator_id}` | "
            f"{_fmt(a.signal_direction)} | {a.signal_strength:.2f} |"
        )
    return rows


def _drivers_block(drivers: list[str]) -> list[str]:
    if not drivers:
        return ["- _(empty)_"]
    return [f"- {d}" for d in drivers]


def _assessment_section(idx: int, a: Assessment) -> list[str]:
    analyst = PERSONA_NAMES.get(a.agent_id, a.agent_id)
    lines: list[str] = [
        f"## {idx}. {analyst} on `{a.indicator_id}`",
        "",
        f"- **Persona:** `{a.agent_id}`",
        f"- **Signal:** {_fmt(a.signal_direction)} (strength {a.signal_strength:.2f})",
        f"- **Target date:** {a.target_date.isoformat()}",
        f"- **Provider:** {_fmt(a.provider)}",
        "",
        "### Diagnosis",
        "",
        _fmt(a.diagnosis),
        "",
        "### Outlook",
        "",
        _fmt(a.outlook),
        "",
        "### Key drivers",
        "",
        *_drivers_block(list(a.key_drivers)),
        "",
        "### News interpretation",
        "",
        _fmt(a.news_interpretation),
        "",
        "### Reasoning trace",
        "",
        _fmt(a.reasoning_trace),
        "",
    ]
    return lines


def render(assessments: list[Assessment], meta: dict) -> str:
    completed_at = meta.get("completed_at") or datetime.now().isoformat(timespec="seconds")
    title = f"# Macro Assessment Run — {completed_at}"

    parts: list[str] = [title, ""]
    parts.extend(_meta_lines(meta))
    parts.extend(["", "## Summary", ""])
    parts.extend(_summary_rows(assessments))
    parts.append("")

    if assessments:
        parts.append("## Assessments")
        parts.append("")
        for idx, a in enumerate(assessments, start=1):
            parts.extend(_assessment_section(idx, a))
    else:
        parts.append("_(no assessments)_")
        parts.append("")

    return "\n".join(parts).rstrip() + "\n"


def default_output_path() -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"./out/run_{ts}.md"


def default_run_dir(run_id: str | None = None) -> str:
    if run_id is None:
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return f"./out/run_{run_id}"


def ensure_parent_dir(path: str | Path) -> Path:
    p = Path(path)
    parent = p.parent if p.suffix else p
    parent.mkdir(parents=True, exist_ok=True)
    return p


def slugify(s: str) -> str:
    """Lowercase kebab-case slug: 'Financial Services' -> 'financial-services'."""
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def run_timestamp() -> str:
    """ISO timestamp safe for filenames (no colons). Includes ms."""
    return datetime.now().strftime("%Y-%m-%dT%H-%M-%S_%f")[:-3]


def output_root(provider: str) -> Path:
    """Return the bucket root for a given provider.

    Real-provider debates land under ``out/real/``; mock debates land under
    ``out/mock/``. An empty or ``"mock"`` provider always routes to
    ``out/mock/``. The user's real analyses (in ``out/real/``) are the only
    ones auto-committed by ``app.main._auto_commit_and_push``.
    """
    bucket = "real" if provider and provider != "mock" else "mock"
    return Path("out") / bucket


def run_dir(domain: str, group: str, target: str, provider: str = "mock") -> Path:
    """Per-target directory that holds all runs for this domain/group/target.

    The output root is derived from ``provider`` via :func:`output_root`,
    so a non-mock provider writes under ``out/real/`` and a mock provider
    writes under ``out/mock/``.
    """
    base = output_root(provider) / domain / slugify(group) / target.upper()
    base.mkdir(parents=True, exist_ok=True)
    return base


def per_agent_dir(
    domain: str, group: str, target: str, provider: str = "mock"
) -> Path:
    p = run_dir(domain, group, target, provider) / "per_agent"
    p.mkdir(parents=True, exist_ok=True)
    return p


def output_path(
    domain: str,
    group: str,
    target: str,
    run_ts: str,
    provider: str,
    kind: str,
    ext: str = "md",
) -> Path:
    """Full path for a single output file."""
    safe_provider = slugify(provider) or "provider"
    return (
        run_dir(domain, group, target, provider)
        / f"{run_ts}_{safe_provider}_{kind}.{ext}"
    )


def _render_single(assessment: Assessment, meta: dict) -> str:
    persona_name = PERSONA_NAMES.get(assessment.agent_id, assessment.agent_id.title())
    indicator_name = assessment.indicator_id
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
    run_id = meta.get("run_id", "")
    lines: list[str] = [
        f"# {persona_name} on {indicator_name}",
        "",
        f"> Generated: {timestamp}",
    ]
    if run_id:
        lines.append(f"> Run: `{run_id}`")
    lines.append(f"> Target date: {assessment.target_date}")
    lines.append(f"> Provider: {assessment.provider}")
    lines.append("")
    lines.append(
        f"- **Signal:** {assessment.signal_direction} ({assessment.signal_strength:.2f})"
    )
    lines.append(f"- **Persona id:** `{assessment.agent_id}`")
    lines.append("")
    lines.append("### Diagnosis")
    lines.append(assessment.diagnosis or "_empty_")
    lines.append("")
    lines.append("### Outlook")
    lines.append(assessment.outlook or "_empty_")
    lines.append("")
    lines.append("### Key drivers")
    if assessment.key_drivers:
        for d in assessment.key_drivers:
            lines.append(f"- {d}")
    else:
        lines.append("_empty_")
    lines.append("")
    lines.append("### News interpretation")
    lines.append(assessment.news_interpretation or "_empty_")
    lines.append("")
    lines.append("### Reasoning trace")
    lines.append(assessment.reasoning_trace or "_empty_")
    lines.append("")
    return "\n".join(lines)


def render_per_agent(
    assessments: list[Assessment], meta: dict
) -> dict[str, list[tuple[str, str]]]:
    grouped: dict[str, list[Assessment]] = {}
    for a in assessments:
        grouped.setdefault(a.agent_id, []).append(a)
    out: dict[str, list[tuple[str, str]]] = {}
    for persona_id, group in sorted(grouped.items()):
        items: list[tuple[str, str]] = []
        for a in sorted(group, key=lambda x: x.indicator_id):
            items.append((a.indicator_id, _render_single(a, meta)))
        out[persona_id] = items
    return out


def render_summary(assessments: list[Assessment], meta: dict) -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
    lines: list[str] = [f"# Run summary — {timestamp}", ""]
    for k in ("target_date", "provider", "analysts", "indicators"):
        if k in meta:
            v = meta[k]
            if isinstance(v, list):
                v = ", ".join(map(str, v))
            lines.append(f"- **{k.replace('_', ' ').title()}:** {v}")
    lines.append(f"- **Total assessments:** {len(assessments)}")
    run_id = meta.get("run_id", "")
    if run_id:
        lines.append(f"- **Run id:** `{run_id}`")
    lines.append("")
    lines.append("## Table")
    lines.append("")
    personas = sorted({a.agent_id for a in assessments})
    indicators = sorted({a.indicator_id for a in assessments})
    lines.append("| Persona | " + " | ".join(indicators) + " |")
    lines.append("|" + "|".join(["---"] * (len(indicators) + 1)) + "|")
    by_persona_indicator = {(a.agent_id, a.indicator_id): a for a in assessments}
    for pid in personas:
        name = PERSONA_NAMES.get(pid, pid.title())
        cells: list[str] = []
        for ind in indicators:
            a = by_persona_indicator.get((pid, ind))
            if a:
                cells.append(f"{a.signal_direction} ({a.signal_strength:.2f})")
            else:
                cells.append("—")
        lines.append(f"| {name} ({pid}) | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("## Files")
    lines.append("")
    for pid in personas:
        for ind in indicators:
            if (pid, ind) in by_persona_indicator:
                lines.append(f"- [{pid}/{ind}.md]({pid}/{ind}.md)")
    lines.append("")
    return "\n".join(lines)


def _verdict_style(direction: Any) -> str:
    name = direction.value if isinstance(direction, Direction) else str(direction)
    if name == Direction.BULLISH.value:
        return "bold green"
    if name == Direction.BEARISH.value:
        return "bold red"
    return "bold yellow"


def _first_line(text: str, limit: int = 80) -> str:
    s = (text or "").strip().splitlines()
    head = s[0] if s else ""
    if len(head) <= limit:
        return head
    return head[: limit - 1] + "…"


def render_debate_rich(result: DebateResult, console: Console | None = None) -> None:
    """Pretty-print a ``DebateResult`` to a (possibly TTY-attached) ``Console``.

    The output is intentionally non-ASCII-tolerant (rich handles color/escape
    codes) and uses a sectioned layout:

      - HEADER (target / domain / date)
      - TABLE: Persona | Round | Verdict | Conviction | Key drivers (first line)
      - SYNTHESIS bullet list (only when ``result.verdict`` is present)
    """
    con = console or Console()

    con.print()
    con.rule(f"[bold cyan]Debate — {result.target} ({result.domain.value})[/bold cyan]")
    meta_parts = [
        f"date: {result.target_date}",
        f"provider: {result.provider}",
        f"analysts: {', '.join(result.analysts)}",
        f"theses: {len(result.theses)}",
        f"rebuttals: {len(result.rebuttals)}",
    ]
    con.print("  " + "  ·  ".join(meta_parts))
    con.print()

    rows: list[tuple[str, int, Any, float, str, str]] = []
    for t in result.theses:
        rows.append((t.agent_id, t.round, t.verdict, t.conviction, _first_line(t.reasoning), "thesis"))
    for rb in result.rebuttals:
        rows.append((rb.agent_id, rb.round, rb.revised_verdict, rb.revised_conviction, _first_line(rb.reasoning), "rebuttal"))

    if rows:
        tbl = Table(title="Positions", show_lines=False, header_style="bold cyan")
        tbl.add_column("Persona", style="bold")
        tbl.add_column("Round", justify="right")
        tbl.add_column("Verdict")
        tbl.add_column("Conviction", justify="right")
        tbl.add_column("Key driver / first line", overflow="fold")
        tbl.add_column("Kind", justify="center")
        for persona, round_idx, verdict, conv, first, kind in rows:
            tbl.add_row(
                PERSONA_NAMES.get(persona, persona),
                str(round_idx),
                f"[{_verdict_style(verdict)}]{verdict.value if isinstance(verdict, Direction) else str(verdict)}[/{_verdict_style(verdict)}]",
                f"{conv:.2f}",
                first,
                kind,
            )
        con.print(tbl)
        con.print()

    if result.verdict is not None:
        v = result.verdict
        con.rule(f"[bold magenta]SYNTHESIS — consensus {v.consensus.value}[/bold magenta]")
        con.print(
            f"  [bold]Final call:[/bold] {v.final_call}    "
            f"[bold]Confidence:[/bold] {v.confidence:.2f}    "
            f"[bold]Avg conviction:[/bold] {v.avg_conviction:.2f}"
        )
        con.print(
            f"  [bold]Tally:[/bold] bull={v.bull_count}  bear={v.bear_count}  neutral={v.neutral_count}"
        )
        if v.points_of_agreement:
            con.print("  [bold green]Points of agreement:[/bold green]")
            for p in v.points_of_agreement:
                con.print(f"    • {p}")
        if v.points_of_disagreement:
            con.print("  [bold red]Points of disagreement:[/bold red]")
            for p in v.points_of_disagreement:
                con.print(f"    • {p}")
        if v.summary:
            con.print("  [bold]Summary:[/bold]")
            for ln in (v.summary or "").splitlines():
                con.print(f"    {ln}" if ln.strip() else "")
        con.print()
