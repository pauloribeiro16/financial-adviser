"""Interactive CLI menu built on beaupy.

Single entry point: ``interactive_pick(defaults) -> dict``.

The flow:
    1.  A ``rich`` welcome panel describing what the tool does.
    2.  Domain (company / macro).
    3.  Target (ticker or comma-separated indicators).
    4.  Provider (mock / minimax).
    5.  Personas (multi-select with display names).
    6.  Rounds (validated number 1-10).
    7.  Output format.
    8.  Synthesis (yes / no).
    9.  Confirmation summary; user can confirm or restart.

If stdout is not a TTY (or beaupy raises for any reason), the function
returns the caller-provided ``defaults`` unchanged so the CLI keeps working
in scripts and CI.
"""

from __future__ import annotations

import sys
from typing import Any

import beaupy
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from app.agents import _PERSONA_DEFS, ALL_AGENTS
from app.logging import get_logger

log = get_logger(__name__)

DEFAULT_COMPANY_ANALYSTS: list[str] = ["buffett", "lynch", "burry", "taleb"]
DEFAULT_MACRO_ANALYSTS: list[str] = ["dalio", "gundlach", "volcker", "greenspan"]
DEFAULT_INDICATORS: list[str] = ["US.FFR", "US.CPI.YOY"]
FORMATS: list[str] = ["debate", "md", "json", "per-agent"]

_PERSONA_NAMES: dict[str, str] = {pid: name for pid, name, *_ in _PERSONA_DEFS}
_PERSONA_SCHOOL: dict[str, str] = {pid: school for pid, _, school, _ in _PERSONA_DEFS}


def _is_tty() -> bool:
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        return False


def _safe(fn: Any, fallback: Any, propagate_cancel: bool = True) -> Any:
    try:
        result = fn()
    except (KeyboardInterrupt, EOFError):
        if propagate_cancel:
            raise
        return fallback
    except Exception as e:
        log.warning("cli_menu.prompt_failed", error=str(e))
        return fallback
    if result is None:
        if propagate_cancel:
            raise KeyboardInterrupt("user cancelled interactive prompt")
        return fallback
    return result


def _render_welcome(console: Console) -> None:
    table = Table.grid(padding=(0, 1))
    table.add_column(style="bold cyan", justify="right")
    table.add_column()
    table.add_row("Goal", "Multi-persona investment debate")
    table.add_row("Domain", "company (ticker)  |  macro (FRED)")
    table.add_row("Engine", "LangChain + Langfuse  |  no DB, no UI")
    table.add_row("Output", "Markdown, JSON, per-agent, or rich table")
    console.print()
    console.print(Panel(
        table,
        title="[bold magenta]Financial Adviser — debate configurator[/]",
        subtitle="[dim]↑/↓ to move · space to toggle · enter to confirm[/]",
        border_style="magenta",
    ))
    console.print()


def _persona_label(pid: str) -> str:
    name = _PERSONA_NAMES.get(pid, pid.title())
    school = _PERSONA_SCHOOL.get(pid, "")
    return f"{name}  ({school})" if school else name


def _validate_rounds(s: str) -> bool:
    try:
        n = int(s)
    except (TypeError, ValueError):
        return False
    return 1 <= n <= 10


def _persona_options(selected_default: list[str]) -> tuple[list[Any], list[int]]:
    pids = sorted(ALL_AGENTS.keys())
    labels = [_persona_label(p) for p in pids]
    ticked = [i for i, p in enumerate(pids) if p in selected_default]
    return labels, ticked


def _render_summary(console: Console, cfg: dict[str, Any]) -> None:
    if cfg["domain"] == "company":
        target_line = f"Ticker       [bold cyan]{cfg['target']}[/]"
    else:
        target_line = f"Indicators   [bold cyan]{', '.join(cfg['indicators'])}[/]"
    personas = ", ".join(cfg["analysts"]) or "[red](none)[/]"
    table = Table.grid(padding=(0, 1))
    table.add_column(style="bold cyan", justify="right")
    table.add_column()
    table.add_row("Domain",    f"[bold]{cfg['domain']}[/]")
    table.add_row("",          target_line)
    table.add_row("Provider",  cfg["provider"])
    table.add_row("Personas",  personas)
    table.add_row("Rounds",    str(cfg["rounds"]))
    table.add_row("Format",    cfg["format"])
    table.add_row("Synthesis", "yes" if cfg["include_synthesis"] else "no")
    console.print()
    console.print(Panel(table, title="[bold yellow]Confirm configuration[/]", border_style="yellow"))
    console.print()


def interactive_pick(defaults: dict[str, Any]) -> dict[str, Any]:
    """Run an interactive beaupy menu and return the chosen options.

    Required keys in ``defaults`` (all consumed with sensible fallbacks):
        - domain: 'company' | 'macro'
        - target: str (ticker for company; first indicator for macro)
        - indicators: list[str] (macro only)
        - provider: 'mock' | 'minimax'
        - analysts: list[str]
        - rounds: int
        - format: 'per-agent' | 'md' | 'json' | 'debate'
        - include_synthesis: bool

    On non-TTY stdout or any prompt failure, returns ``defaults`` unchanged.
    """
    defaults = dict(defaults or {})
    if not _is_tty():
        return defaults

    console = Console()
    _render_welcome(console)

    domain_options = [
        "Company  (evaluate a ticker via SEC EDGAR + yfinance)",
        "Macro    (evaluate a FRED indicator)",
    ]
    default_domain = defaults.get("domain", "company")
    domain_idx = 0 if default_domain != "macro" else 1
    picked_idx = _safe(
        lambda: beaupy.select(domain_options, cursor=">", cursor_index=domain_idx, pagination=False, return_index=True),
        domain_idx,
    )
    domain = "company" if picked_idx == 0 else "macro"

    if domain == "company":
        default_target = str(defaults.get("target") or "AAPL")
        ticker_raw = _safe(
            lambda: beaupy.prompt("Ticker (e.g. AAPL, MSFT, NVDA)", initial_value=default_target),
            default_target,
        )
        ticker = str(ticker_raw).upper().strip() or "AAPL"
        target = ticker
        indicators: list[str] = []
    else:
        default_indicators = list(defaults.get("indicators") or DEFAULT_INDICATORS)
        ind_raw = _safe(
            lambda: beaupy.prompt("Indicators (comma-separated)", initial_value=",".join(default_indicators)),
            ",".join(default_indicators),
        )
        indicators = [s.strip() for s in str(ind_raw).split(",") if s.strip()] or list(default_indicators)
        target = indicators[0]

    provider_options = [
        "mock      (offline, no API key)",
        "minimax   (real API, requires MINIMAX_API_KEY)",
    ]
    default_provider = defaults.get("provider", "mock")
    provider_idx = 0 if default_provider != "minimax" else 1
    picked_idx = _safe(
        lambda: beaupy.select(provider_options, cursor=">", cursor_index=provider_idx, pagination=False, return_index=True),
        provider_idx,
    )
    provider = "mock" if picked_idx == 0 else "minimax"

    persona_labels, ticked = _persona_options(
        list(defaults.get("analysts") or (DEFAULT_COMPANY_ANALYSTS if domain == "company" else DEFAULT_MACRO_ANALYSTS))
    )
    picked_indices = _safe(
        lambda: beaupy.select_multiple(
            persona_labels,
            ticked_indices=ticked,
            minimal_count=1,
            pagination=True,
            page_size=12,
            return_indices=True,
        ),
        ticked,
    )
    pids_sorted = sorted(ALL_AGENTS.keys())
    if picked_indices:
        analysts = [pids_sorted[i] for i in picked_indices]
    else:
        analysts = DEFAULT_COMPANY_ANALYSTS if domain == "company" else DEFAULT_MACRO_ANALYSTS

    default_rounds = int(defaults.get("rounds", 2))
    rounds_raw = _safe(
        lambda: beaupy.prompt(
            "Rounds (1-10)",
            validator=_validate_rounds,
            initial_value=str(default_rounds),
        ),
        str(default_rounds),
    )
    try:
        rounds = int(rounds_raw)
    except (TypeError, ValueError):
        rounds = default_rounds

    format_options = [
        "debate      (Markdown, round-by-round + synthesis)",
        "md          (single Markdown file)",
        "json        (structured JSON)",
        "per-agent   (one file per persona)",
    ]
    default_format = defaults.get("format", "debate")
    fmt_idx = FORMATS.index(default_format) if default_format in FORMATS else 0
    picked_idx = _safe(
        lambda: beaupy.select(format_options, cursor=">", cursor_index=fmt_idx, pagination=False, return_index=True),
        fmt_idx,
    )
    fmt = FORMATS[picked_idx]

    synth_default = bool(defaults.get("include_synthesis", True))
    synth = _safe(
        lambda: beaupy.confirm("Include synthesis (moderator verdict)?", default_is_yes=synth_default),
        synth_default,
    )
    include_synthesis = bool(synth)

    cfg = {
        "domain": domain,
        "target": target,
        "indicators": indicators,
        "provider": provider,
        "analysts": analysts,
        "rounds": rounds,
        "format": fmt,
        "include_synthesis": include_synthesis,
    }

    _render_summary(console, cfg)
    confirm = _safe(
        lambda: beaupy.confirm("Run with this configuration?", default_is_yes=True),
        True,
        propagate_cancel=False,
    )
    if not confirm:
        log.info("cli_menu.user_cancelled_after_summary")
        raise KeyboardInterrupt("user cancelled after summary")

    return cfg
