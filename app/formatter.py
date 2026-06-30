from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.models import Assessment

__all__ = ["render", "default_output_path", "PERSONA_NAMES"]

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


def ensure_parent_dir(path: str | Path) -> Path:
    p = Path(path)
    parent = p.parent if p.suffix else p
    parent.mkdir(parents=True, exist_ok=True)
    return p
