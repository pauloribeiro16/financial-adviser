from __future__ import annotations

from pathlib import Path

from app.cli_menu import SECTOR_TICKERS
from app.logging import get_logger
from app.sectors import available_sectors, load_sector, slug_for

log = get_logger(__name__)


def _resolve_sector_slug(sector: str | None) -> str | None:
    if sector is None:
        return None
    slug = slug_for(sector)
    if slug in available_sectors():
        return slug
    return None


def cmd_watch(
    sector: str | None = None,
    ticker: str | None = None,
    all_sectors: bool = False,
    provider: str = "mock",
    output: Path | None = None,
) -> int:
    """Sub-command scaffold for `python -m app.main watch ...`.

    P1 scope: argument validation + logging only. The full orchestrator
    (aggregator + renderer + Langfuse trace) lands in S14-P2 / P3.
    """
    if not all_sectors and sector is None:
        log.warning("watch.cli.no_sector_specified")
        print(
            "ERROR: --sector <name> or --all is required. "
            f"Available sectors: {', '.join(sorted(SECTOR_TICKERS.keys()))}",
        )
        return 1

    if sector is not None and all_sectors:
        log.warning("watch.cli.mutually_exclusive")
        print("ERROR: --sector and --all are mutually exclusive.", file=__import__("sys").stderr)
        return 2

    if sector is not None:
        slug = _resolve_sector_slug(sector)
        if slug is None:
            print(
                f"ERROR: unknown sector {sector!r}. "
                f"Available: {', '.join(sorted(SECTOR_TICKERS.keys()))}",
            )
            return 1
        indicators = load_sector(slug)
        log.info(
            "watch.cli.sector_resolved",
            sector=sector,
            slug=slug,
            n_indicators=len(indicators),
            provider=provider,
            ticker=ticker,
            output=str(output) if output else None,
        )
        print(
            f"[watch:placeholder] sector={sector} (slug={slug}) "
            f"provider={provider} ticker={ticker} indicators={len(indicators)} "
            f"output={output}"
        )
        return 0

    slugs = available_sectors()
    log.info(
        "watch.cli.all_sectors_resolved",
        n_sectors=len(slugs),
        provider=provider,
        output=str(output) if output else None,
    )
    print(
        f"[watch:placeholder] all_sectors=True slugs={slugs} "
        f"provider={provider} output={output}"
    )
    return 0
