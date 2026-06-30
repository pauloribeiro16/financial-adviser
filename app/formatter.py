from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.models import Assessment

__all__ = [
    "render",
    "render_per_agent",
    "render_summary",
    "default_output_path",
    "default_run_dir",
    "ensure_parent_dir",
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
