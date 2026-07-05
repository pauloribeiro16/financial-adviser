from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from app.cli_menu import SECTOR_TICKERS
from app.logging import get_logger
from app.pipeline import cache
from app.sectors import load_sector
from app.watch.aggregator import aggregate_one
from app.watch.langfuse_tracing import surveillance_trace
from app.watch.markdown_renderer import (
    fundamentals_dict_for_ticker,
    indicator_rows_for_ticker,
    render_company_current_md,
)
from app.watch.price_target import compute_buy_price, moat_strength_from_text
from app.watch.reference_reader import load_latest_debate
from app.watch.sector_file import append_history, write_sector_index

log = get_logger(__name__)

_MAX_WORKERS = 4
_SECTOR_TARGET_FCF_YIELD_DEFAULT = 0.05


def _sector_target_fcf_yield(sector: str) -> float:
    if sector.lower() == "energy":
        return 0.06
    if sector.lower() == "technology":
        return 0.04
    if sector.lower() == "healthcare":
        return 0.045
    if sector.lower() in {"financial-services", "financial services"}:
        return 0.07
    return _SECTOR_TARGET_FCF_YIELD_DEFAULT


def _company_fcf_yield(ticker: str) -> float | None:
    market = cache.get("market", ticker.upper(), ttl_seconds=24 * 3600) or {}
    fundamentals = cache.get("fundamentals", ticker.upper(), ttl_seconds=24 * 3600) or {}
    cf_rows = fundamentals.get("cashflow") or []
    latest_cf = cf_rows[0] if cf_rows else {}
    fcf = latest_cf.get("Free Cash Flow")
    mcap = market.get("market_cap")
    if fcf is None or not mcap:
        return None
    try:
        return float(fcf) / float(mcap)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _current_price(ticker: str) -> float:
    market = cache.get("market", ticker.upper(), ttl_seconds=24 * 3600) or {}
    price = market.get("price")
    if price is None:
        return 0.0
    try:
        return float(price)
    except (TypeError, ValueError):
        return 0.0


def _process_one_ticker(
    ticker: str,
    name: str,
    sector: str,
    sector_slug: str,
    provider_name: str,
    output_root: Path,
    specs: list[Any],
    sector_target_yield: float,
) -> tuple[str, Path | None, dict[str, Any] | None]:
    log.info("watch.sector_runner.ticker_start", ticker=ticker, sector=sector)
    ref = load_latest_debate(sector, ticker)
    if ref is None:
        log.warning(
            "watch.sector_runner.no_debate",
            ticker=ticker,
            sector=sector,
        )
        return ticker, None, None

    summary = aggregate_one(provider_name, ref, ticker, sector, fundamentals=fundamentals_dict_for_ticker(ticker, specs))
    rows = indicator_rows_for_ticker(ticker, specs)
    company_yield = _company_fcf_yield(ticker)
    current_price = _current_price(ticker)
    moat_strength = moat_strength_from_text(summary.moat)
    sector_yield_for_calc = company_yield if company_yield else sector_target_yield
    buy_price = compute_buy_price(
        current_price=current_price or 0.0,
        sector_target_fcf_yield=sector_yield_for_calc or sector_target_yield,
        company_fcf_yield=company_yield or sector_target_yield,
        moat_strength=moat_strength,
    )

    md = render_company_current_md(
        summary=summary,
        ticker=ticker,
        sector=sector,
        debate_ref=ref,
        indicator_rows=rows,
        buy_price=buy_price,
        sector_target_fcf_yield=sector_target_yield,
        current_price=current_price,
        indicator_specs=specs,
        moat_strength=moat_strength,
    )

    ticker_dir = output_root / sector_slug / ticker.upper()
    ticker_dir.mkdir(parents=True, exist_ok=True)
    out_path = ticker_dir / "current.md"
    out_path.write_text(md, encoding="utf-8")

    append_history(
        sector=sector,
        ticker=ticker,
        record={
            "provider": provider_name,
            "buy_price": buy_price,
            "current_price": current_price,
            "company_fcf_yield": company_yield,
            "sector_target_fcf_yield": sector_target_yield,
            "moat_strength": moat_strength,
            "summary": summary.model_dump(),
            "debate_session": ref.debate_path.stem,
        },
        output_root=output_root,
    )

    log.info(
        "watch.sector_runner.ticker_done",
        ticker=ticker,
        sector=sector,
        path=str(out_path),
        buy_price=buy_price,
    )

    from app.watch.markdown_renderer import _conv_from_summary, _verdict_from_summary

    entry = {
        "ticker": ticker.upper(),
        "name": name,
        "verdict": _verdict_from_summary(summary),
        "buy_price": buy_price,
        "conviction": _conv_from_summary(summary),
        "last_updated": ref.debate_path.stem.split("_")[0],
        "path": str(out_path),
    }
    return ticker, out_path, entry


def _resolve_ticker_pairs(sector: str, tickers: list[str] | None) -> list[tuple[str, str]]:
    sector_pairs = SECTOR_TICKERS.get(sector, [])
    name_by_symbol = {sym.upper(): name for sym, name in sector_pairs}
    if tickers is None:
        return list(sector_pairs)
    resolved: list[tuple[str, str]] = []
    for raw in tickers:
        sym = raw.strip().upper()
        if not sym:
            continue
        resolved.append((sym, name_by_symbol.get(sym, sym)))
    return resolved


def run_sector(
    sector: str,
    provider_name: str,
    output_root: Path = Path("./out/surveillance"),
    tickers: list[str] | None = None,
) -> dict[str, Path]:
    if sector not in SECTOR_TICKERS:
        log.error("watch.sector_runner.unknown_sector", sector=sector)
        raise FileNotFoundError(
            f"Unknown sector {sector!r}. Available: {sorted(SECTOR_TICKERS.keys())}"
        )

    sector_slug = sector.lower().replace(" ", "-")
    specs = load_sector(sector_slug)
    sector_target_yield = _sector_target_fcf_yield(sector)
    ticker_pairs = _resolve_ticker_pairs(sector, tickers)
    log.info(
        "watch.sector_runner.start",
        sector=sector,
        provider=provider_name,
        n_tickers=len(ticker_pairs),
        output_root=str(output_root),
        tickers_override=tickers,
    )

    output_root.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    outputs: dict[str, Path] = {}

    with surveillance_trace(sector) as trace:
        log.info(
            "watch.sector_runner.trace_active",
            sector=sector,
            enabled=trace.enabled,
        )
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as ex:
            futures = {
                ex.submit(
                    _process_one_ticker,
                    ticker,
                    name,
                    sector,
                    sector_slug,
                    provider_name,
                    output_root,
                    specs,
                    sector_target_yield,
                ): ticker
                for ticker, name in ticker_pairs
            }
            for fut in as_completed(futures):
                ticker = futures[fut]
                try:
                    tkr, out_path, entry = fut.result()
                except Exception as e:
                    log.error(
                        "watch.sector_runner.ticker_failed",
                        ticker=ticker,
                        error=str(e),
                    )
                    continue
                if out_path is not None:
                    outputs[tkr] = out_path
                if entry is not None:
                    entries.append(entry)

    entries.sort(key=lambda e: e["ticker"])
    index_path = write_sector_index(sector, entries, output_root)
    log.info(
        "watch.sector_runner.complete",
        sector=sector,
        n_outputs=len(outputs),
        index=str(index_path),
    )
    return outputs


__all__ = ["run_sector"]
