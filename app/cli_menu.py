"""Interactive CLI menu built on beaupy.

Single entry point: ``interactive_pick(defaults) -> dict``.

The flow is entirely arrow-key driven — no free-text input. Every choice
is a ``beaupy.select`` (single) or ``beaupy.select_multiple``:

    1.  A ``rich`` welcome panel describing what the tool does.
    2.  Domain (company / macro).
    3.  Target (ticker from a popular list OR indicators from the FRED catalog).
    4.  Provider (mock / minimax).
    5.  Personas (multi-select with display names).
    6.  Rounds (1..10, single select).
    7.  Output format.
    8.  Synthesis (yes / no).
    9.  Confirmation summary; user can confirm or abort.

If stdout is not a TTY (or beaupy raises for any reason), the function
returns the caller-provided ``defaults`` unchanged so the CLI keeps
working in scripts and CI.
"""

from __future__ import annotations

import sys
from typing import Any

import beaupy
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from app.agents import _PERSONA_DEFS, personas_for_domain
from app.catalog import get_catalog
from app.logging import get_logger

log = get_logger(__name__)

DEFAULT_COMPANY_ANALYSTS: list[str] = ["buffett", "lynch", "burry", "taleb"]
DEFAULT_MACRO_ANALYSTS: list[str] = ["dalio", "gundlach", "volcker", "greenspan"]
DEFAULT_INDICATORS: list[str] = ["US.FFR", "US.CPI.YOY"]
FORMATS: list[str] = ["debate", "md", "json", "per-agent"]

SECTOR_DEFAULT_ANALYSTS: dict[str, list[str]] = {
    "Financial Services": ["buffett", "lynch", "burry", "dimon"],
    "Technology":        ["buffett", "lynch", "wood", "taleb"],
    "Healthcare":        ["buffett", "lynch", "grantham", "taleb"],
    "Energy":            ["buffett", "dalio", "eisman", "taleb"],
}

SECTOR_TICKERS: dict[str, list[tuple[str, str]]] = {
    "Financial Services": [
        ("JPM",  "JPMorgan Chase"),
        ("BAC",  "Bank of America"),
        ("GS",   "Goldman Sachs"),
        ("MS",   "Morgan Stanley"),
        ("WFC",  "Wells Fargo"),
        ("V",    "Visa"),
        ("MA",   "Mastercard"),
        ("BLK",  "BlackRock"),
    ],
    "Technology": [
        ("AAPL", "Apple"),
        ("MSFT", "Microsoft"),
        ("NVDA", "NVIDIA"),
        ("GOOGL","Alphabet"),
        ("META", "Meta Platforms"),
        ("ADBE", "Adobe"),
        ("CRM",  "Salesforce"),
        ("AVGO", "Broadcom"),
    ],
    "Healthcare": [
        ("JNJ",  "Johnson & Johnson"),
        ("UNH",  "UnitedHealth Group"),
        ("LLY",  "Eli Lilly"),
        ("PFE",  "Pfizer"),
        ("ABBV", "AbbVie"),
        ("MRK",  "Merck"),
        ("TMO",  "Thermo Fisher Scientific"),
    ],
    "Energy": [
        ("XOM",  "ExxonMobil"),
        ("CVX",  "Chevron"),
        ("COP",  "ConocoPhillips"),
        ("SLB",  "Schlumberger"),
        ("EOG",  "EOG Resources"),
        ("MPC",  "Marathon Petroleum"),
    ],
}

POPULAR_TICKERS: list[tuple[str, str]] = [
    ticker for sector in SECTOR_TICKERS.values() for ticker in sector
]

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


def _indicator_options() -> tuple[list[str], list[str], list[int]]:
    """Return (labels, ids, pre-ticked indices) from the FRED catalog."""
    catalog = get_catalog()
    labels = [f"{i.indicator_id}  —  {i.name}  [dim]({i.category.value.lower()})[/]" for i in catalog]
    ids = [i.indicator_id for i in catalog]
    return labels, ids, []


def _persona_options(
    available_pids: list[str], selected_default: list[str]
) -> tuple[list[str], list[int]]:
    labels = [_persona_label(p) for p in available_pids]
    ticked = [i for i, p in enumerate(available_pids) if p in selected_default]
    return labels, ticked


def _fallback_analysts(domain: str, available: list[str]) -> list[str]:
    defaults = DEFAULT_COMPANY_ANALYSTS if domain == "company" else DEFAULT_MACRO_ANALYSTS
    filtered = [p for p in defaults if p in available]
    if filtered:
        return filtered
    return available[:3]


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

    All choices are arrow-key based; there is no free-text input anywhere.
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
    Returned dict always carries a ``mode`` key ('analyze' | 'watch').
    """
    defaults = dict(defaults or {})
    if not _is_tty():
        defaults.setdefault("mode", "analyze")
        return defaults

    console = Console()
    _render_welcome(console)

    mode_options = [
        "Analyze  (run a debate on a target)",
        "Watch    (refresh surveillance table)",
    ]
    default_mode = str(defaults.get("mode", "analyze"))
    mode_idx = 1 if default_mode == "watch" else 0
    picked_idx = _safe(
        lambda: beaupy.select(
            mode_options,
            cursor=">",
            cursor_index=mode_idx,
            pagination=False,
            return_index=True,
        ),
        mode_idx,
    )
    mode = "watch" if picked_idx == 1 else "analyze"

    if mode == "watch":
        sector_labels = list(SECTOR_TICKERS.keys())
        default_sector = defaults.get("sector") or next(
            (sec for sec, tickers in SECTOR_TICKERS.items()
             if any(sym == str(defaults.get("target") or "").upper()
                    for sym, _ in tickers)),
            "Energy",
        )
        sector_idx = (
            sector_labels.index(default_sector)
            if default_sector in sector_labels
            else 0
        )
        picked_idx = _safe(
            lambda: beaupy.select(
                sector_labels,
                cursor=">",
                cursor_index=sector_idx,
                pagination=False,
                return_index=True,
            ),
            sector_idx,
        )
        picked_sector = sector_labels[picked_idx]

        provider_options = [
            "mock      (offline, no API key)",
            "minimax   (real API, requires MINIMAX_API_KEY)",
        ]
        default_provider = str(defaults.get("provider", "mock"))
        provider_idx = 0 if default_provider != "minimax" else 1
        picked_idx = _safe(
            lambda: beaupy.select(
                provider_options,
                cursor=">",
                cursor_index=provider_idx,
                pagination=False,
                return_index=True,
            ),
            provider_idx,
        )
        provider = "mock" if picked_idx == 0 else "minimax"

        single_yes_no = _safe(
            lambda: beaupy.confirm(
                f"Refresh a single ticker in {picked_sector}?",
                default_is_yes=False,
            ),
            False,
            propagate_cancel=False,
        )

        cfg = {
            "mode": "watch",
            "domain": "company",
            "sector": picked_sector,
            "all_sectors": False,
            "single_ticker": bool(single_yes_no),
            "target": str(defaults.get("target") or "XOM"),
            "provider": provider,
            "indicators": [],
            "analysts": list(defaults.get("analysts") or []),
            "rounds": int(defaults.get("rounds", 2)),
            "format": "debate",
            "include_synthesis": True,
        }
        return cfg

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

    selected_sector: str | None = None
    if domain == "company":
        sector_labels = list(SECTOR_TICKERS.keys())
        default_target = str(defaults.get("target") or "AAPL").upper()
        default_sector = next(
            (sec for sec, tickers in SECTOR_TICKERS.items()
             if any(t == default_target for t, _ in tickers)),
            "Financial Services",
        )
        sector_idx = sector_labels.index(default_sector) if default_sector in sector_labels else 0
        picked_idx = _safe(
            lambda: beaupy.select(
                sector_labels,
                cursor=">",
                cursor_index=sector_idx,
                pagination=False,
                return_index=True,
            ),
            sector_idx,
        )
        selected_sector = sector_labels[picked_idx]
        sector_picks = SECTOR_TICKERS[selected_sector]

        ticker_labels = [f"{sym}  ({name})" for sym, name in sector_picks]
        ticker_idx = next(
            (i for i, (sym, _) in enumerate(sector_picks) if sym == default_target),
            0,
        )
        picked_idx = _safe(
            lambda: beaupy.select(
                ticker_labels,
                cursor=">",
                cursor_index=ticker_idx,
                pagination=True,
                page_size=10,
                return_index=True,
            ),
            ticker_idx,
        )
        ticker = sector_picks[picked_idx][0]
        target = ticker
        indicators: list[str] = []
    else:
        indicator_labels, indicator_ids, _ = _indicator_options()
        default_indicators = list(defaults.get("indicators") or DEFAULT_INDICATORS)
        ticked_idx = [
            i for i, iid in enumerate(indicator_ids) if iid in default_indicators
        ] or [0, 1]
        picked_indices = _safe(
            lambda: beaupy.select_multiple(
                indicator_labels,
                ticked_indices=ticked_idx,
                minimal_count=1,
                pagination=True,
                page_size=8,
                return_indices=True,
            ),
            ticked_idx,
        )
        indicators = [indicator_ids[i] for i in picked_indices] if picked_indices else list(default_indicators)
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

    available_pids = personas_for_domain(
        domain,
        selected_sector if domain == "company" else None,
    )
    sector_default = (
        SECTOR_DEFAULT_ANALYSTS.get(selected_sector, [])
        if domain == "company" and selected_sector
        else []
    )
    default_analysts = list(
        defaults.get("analysts")
        or sector_default
        or (DEFAULT_COMPANY_ANALYSTS if domain == "company" else DEFAULT_MACRO_ANALYSTS)
    )
    filtered_default = [p for p in default_analysts if p in available_pids]
    persona_labels, ticked = _persona_options(available_pids, filtered_default)
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
    if picked_indices:
        analysts = [available_pids[i] for i in picked_indices]
    else:
        analysts = _fallback_analysts(domain, available_pids)

    rounds_options = [str(n) for n in range(1, 11)]
    default_rounds = int(defaults.get("rounds", 2))
    rounds_idx = max(0, min(9, default_rounds - 1))
    picked_idx = _safe(
        lambda: beaupy.select(
            rounds_options,
            cursor=">",
            cursor_index=rounds_idx,
            pagination=False,
            return_index=True,
        ),
        rounds_idx,
    )
    rounds = picked_idx + 1

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
        "mode": "analyze",
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
