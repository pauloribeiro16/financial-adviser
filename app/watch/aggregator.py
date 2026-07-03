from __future__ import annotations

from pydantic import BaseModel, Field

from app.debate.engine import _invoke_with_fallback
from app.logging import get_logger
from app.providers import ProviderRegistry
from app.watch.reference_reader import DebateRef

log = get_logger(__name__)

_MAX_DEBATE_CHARS = 16000
_PLACEHOLDER = "Data unavailable"


class WatchSummary(BaseModel):
    moat: str = Field(..., max_length=200)
    cycle_phase: str = Field(..., max_length=200)
    financial_health: str = Field(..., max_length=200)
    valuation: str = Field(..., max_length=200)
    risks: str = Field(..., max_length=400)
    providers_used: str | None = None


def _placeholder_summary(provider_name: str | None = None) -> WatchSummary:
    return WatchSummary(
        moat=_PLACEHOLDER,
        cycle_phase=_PLACEHOLDER,
        financial_health=_PLACEHOLDER,
        valuation=_PLACEHOLDER,
        risks=_PLACEHOLDER,
        providers_used=provider_name,
    )


def _read_debate_text(ref: DebateRef) -> str:
    try:
        return ref.debate_path.read_text(encoding="utf-8")
    except Exception as e:
        log.warning("watch.aggregator.read_failed", path=str(ref.debate_path), error=str(e))
        return ""


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    head = text[: int(max_chars * 0.7)]
    tail = text[-int(max_chars * 0.2) :]
    return f"{head}\n\n[... truncated to {max_chars} chars ...]\n\n{tail}"


def _build_messages(
    ticker: str,
    sector: str,
    debate_text: str,
    *,
    repair: bool = False,
) -> list[dict[str, str]]:
    truncated = _truncate(debate_text, _MAX_DEBATE_CHARS)
    system = (
        "You are a surveillance analyst. Read the debate transcript below and "
        "produce a structured 5-bullet summary that captures the company's "
        "investment posture. Each bullet must be <=200 characters (risks "
        "<=400), be grounded in the debate text, and never invent numbers "
        "that are not present in the transcript. Use traffic-light emojis "
        "(green / yellow / red) when natural, and prefer concrete language "
        "over generic platitudes."
    )
    if repair:
        system += (
            "\n\nIMPORTANT — repair mode. Your previous attempt failed "
            "validation. Return all five fields, each a non-empty string. "
            "Keep the character caps: moat / cycle_phase / financial_health / "
            "valuation <=200 chars; risks <=400 chars."
        )
    user = (
        f"# Target\n- Ticker: {ticker}\n- Sector: {sector}\n\n"
        "# Debate transcript\n"
        f"{truncated}\n\n"
        "# Required JSON fields\n"
        "- moat: the company's competitive advantage in 1-2 short sentences\n"
        "- cycle_phase: where we are in the sector cycle (Hyper-Growth / "
        "Operating Leverage / Capital Return / Decline)\n"
        "- financial_health: balance sheet + FCF + leverage in 1 sentence\n"
        "- valuation: cheap / fair / rich vs sector, with anchor if mentioned\n"
        "- risks: the 1-3 most concrete risks discussed, separated by ' | '\n"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def aggregate_one(
    provider_name: str,
    debate_ref: DebateRef,
    ticker: str,
    sector: str,
) -> WatchSummary:
    provider = ProviderRegistry.get(provider_name)
    debate_text = _read_debate_text(debate_ref)
    if not debate_text.strip():
        log.warning(
            "watch.aggregate.empty_debate",
            ticker=ticker,
            sector=sector,
            path=str(debate_ref.debate_path),
        )
        log.info(
            "watch.aggregate.failed",
            ticker=ticker,
            sector=sector,
            reason="empty_debate",
            provider=provider_name,
        )
        return _placeholder_summary(provider_name=provider_name)

    msgs = _build_messages(ticker, sector, debate_text, repair=False)
    result = _invoke_with_fallback(provider, WatchSummary, msgs)

    if result is None or not isinstance(result, WatchSummary):
        log.warning(
            "watch.aggregate.repair_attempt",
            ticker=ticker,
            sector=sector,
            provider=provider_name,
        )
        repair_msgs = _build_messages(ticker, sector, debate_text, repair=True)
        result = _invoke_with_fallback(provider, WatchSummary, repair_msgs)

    if result is None or not isinstance(result, WatchSummary):
        log.warning(
            "watch.aggregate.failed",
            ticker=ticker,
            sector=sector,
            provider=provider_name,
            reason="double_fallback",
        )
        return _placeholder_summary(provider_name=provider_name)

    summary = result.model_copy(update={"providers_used": provider_name})
    log.info(
        "watch.aggregate.done",
        ticker=ticker,
        sector=sector,
        provider=provider_name,
        moat_len=len(summary.moat),
        risks_len=len(summary.risks),
    )
    return summary


__all__ = ["WatchSummary", "aggregate_one"]
