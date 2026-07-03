from __future__ import annotations

import sys
from pathlib import Path

from app.cli_menu import SECTOR_TICKERS
from app.logging import get_logger
from app.sectors import available_sectors, slug_for
from app.watch.sector_runner import run_sector

log = get_logger(__name__)


def _resolve_sector_slug(sector: str | None) -> str | None:
    if sector is None:
        return None
    slug = slug_for(sector)
    if slug in available_sectors():
        return slug
    return None


def _resolve_tickers(sector: str, ticker: str | None) -> list[str]:
    if ticker:
        return [ticker.strip().upper()]
    return [t for t, _ in SECTOR_TICKERS[sector]]


def _print_watch_help() -> None:
    help_text = (
        "Usage: python -m app.main watch "
        "[--sector NAME | --ticker SYM | --all] "
        "[--provider {mock,minimax}] "
        "[--output DIR]\n\n"
        "Refresh surveillance tables for a sector (S14).\n\n"
        "Options:\n"
        "  --sector NAME     Sector name (e.g. Energy, Technology, Healthcare, "
        "Financial Services).\n"
        "  --ticker SYM      Single ticker to refresh (requires --sector).\n"
        "  --all             Refresh every known sector instead of one.\n"
        "  --provider NAME   LLM provider (default: mock).\n"
        "  --output DIR      Output root directory (default: ./out/surveillance).\n\n"
        f"Available sectors: {', '.join(sorted(SECTOR_TICKERS.keys()))}\n"
    )
    print(help_text)


def cmd_watch(
    sector: str | None = None,
    ticker: str | None = None,
    all_sectors: bool = False,
    provider: str = "mock",
    output: Path | None = None,
) -> int:
    """Refresh surveillance tables for one sector, one ticker, or all sectors.

    Wired up in S14-P3 to drive :func:`run_sector`. CLI flags accept:

    - ``--sector NAME`` (single sector; mutually exclusive with ``--all``)
    - ``--ticker SYM`` (optional; scopes the run to a single ticker)
    - ``--all`` (refresh every known sector)
    - ``--provider NAME`` (mock or minimax)
    - ``--output PATH`` (root directory; default ``./out/surveillance``)

    When invoked with no operation flag (``--sector``, ``--ticker``, ``--all``),
    prints concise help and exits 0 (per S14-P3 OC25).
    """
    output_root = output or Path("./out/surveillance")

    no_op_specified = (
        sector is None and ticker is None and not all_sectors
    )
    if no_op_specified:
        _print_watch_help()
        return 0

    if sector is not None and all_sectors:
        log.warning("watch.cli.mutually_exclusive")
        print("ERROR: --sector and --all are mutually exclusive.", file=sys.stderr)
        return 2

    sectors: list[str]
    if all_sectors:
        sectors = sorted(SECTOR_TICKERS.keys())
    else:
        assert sector is not None
        if sector not in SECTOR_TICKERS:
            print(
                f"ERROR: unknown sector '{sector}'. "
                f"Available: {', '.join(sorted(SECTOR_TICKERS.keys()))}",
                file=sys.stderr,
            )
            return 1
        sectors = [sector]

    total_paths = 0
    for s in sectors:
        ts = _resolve_tickers(s, ticker)
        slug = _resolve_sector_slug(s) or s.lower().replace(" ", "-")
        log.info(
            "watch.sector.start",
            sector=s,
            slug=slug,
            tickers=ts,
            provider=provider,
            output=str(output_root),
        )
        try:
            written: dict[str, Path] = run_sector(
                s,
                provider_name=provider,
                output_root=output_root,
                tickers=ts,
            )
        except FileNotFoundError as e:
            log.error("watch.sector.failed", sector=s, error=str(e))
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        except Exception as e:  # noqa: BLE001
            log.error("watch.sector.failed", sector=s, error=str(e))
            print(f"ERROR: sector {s!r} failed: {e}", file=sys.stderr)
            return 1

        total_paths += len(written)
        for _tkr, path in sorted(written.items()):
            print(f"  written {path}", file=sys.stderr)
        if not written:
            print(
                f"  sector {s}: no tickers had debates; nothing written",
                file=sys.stderr,
            )

    print(
        f"\nDone: {total_paths} surveillance entries under {output_root}.",
        file=sys.stderr,
    )
    log.info(
        "watch.complete",
        total_entries=total_paths,
        provider=provider,
        output=str(output_root),
    )
    return 0


__all__ = ["cmd_watch"]
