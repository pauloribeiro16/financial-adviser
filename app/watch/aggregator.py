from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.debate.engine import _invoke_with_fallback
from app.logging import get_logger
from app.providers import ProviderRegistry
from app.watch.reference_reader import DebateRef

log = get_logger(__name__)

_MAX_DEBATE_CHARS = 16000
_PLACEHOLDER_MOAT = "🟡 Data unavailable for moat assessment"
_PLACEHOLDER_RISKS = "Data unavailable for risk assessment"


class CyclePhase(StrEnum):
    HYPER_GROWTH = "Hyper-Growth"
    OPERATING_LEVERAGE = "Operating Leverage"
    CAPITAL_RETURN = "Capital Return"
    DECLINE = "Decline"


class WatchSummary(BaseModel):
    moat: str = Field(..., max_length=200)
    cycle_phase: CyclePhase
    financial_health: str = Field(..., max_length=200)
    valuation: str = Field(..., max_length=200)
    risks: str = Field(..., max_length=400)
    providers_used: str | None = None

    @field_validator("moat")
    @classmethod
    def _moat_starts_with_traffic_light(cls, v: str) -> str:
        s = v.lstrip()
        if not s or s[0] not in "🟢🟡🔴":
            raise ValueError(
                "moat must start with exactly one of 🟢 (strong/widening), "
                "🟡 (moderate/stable), or 🔴 (weak/narrowing)"
            )
        return v


_DO_NOT_BLOCK = """\
DO NOT:
- Do NOT use hedge language ("it appears", "one might argue", "it seems likely", "there could be"). State facts from the transcript or snapshot. If uncertain, omit.
- Do NOT invent numbers that are not in the transcript or fundamentals snapshot.
- Do NOT write generic platitudes ("strong fundamentals", "solid management", "attractive valuation"). Every claim must cite a specific data point.
- Do NOT embed numbered lists (1. 2. 3.) inside a single field. Use prose.
- Do NOT comment on the debate process ("the analysts discussed", "Buffett argued that", "as noted in the transcript"). You are writing a surveillance report, not summarising the debate.
- Do NOT give buy/sell recommendations or ratings. Surveillance is descriptive.
- Do NOT add disclaimers ("not investment advice", "past performance"). Implied.
- Do NOT start every bullet with the company name. Ticker is in the header.
- Do NOT repeat the same point with different words in the same bullet.
- Do NOT use negation hedges ("not insignificant", "not without risk", "notably stable"). State directly.
- Do NOT stack synonyms ("robust durable sustainable competitive"). Pick one precise word.
- Do NOT use emojis outside the moat field's required leading 🟢/🟡/🔴.
- Do NOT use filler connectors ("Moreover", "Furthermore", "Additionally", "In addition to this").
- Do NOT pad with generic language. If you cannot be concrete, write "Insufficient data to assess" — never pad.
"""


_EXAMPLE_BLOCK = """\
<example>
Input context:
- Ticker: XOM
- Sector: Energy
- Fundamentals snapshot: Current price: $114.50 | FCF yield: 6.4% | Net Debt/EBITDA: 0.39x | Capex/Revenue: 27% | Dividend yield: 3.01% | Share Count YoY: +2.4%
- Debate transcript: 6 analysts (dalio, gundlach, buffett, burry, eisman, taleb) over 2 rounds. Consensus NEUTRAL with conviction 0.45.

Expected output:
{
  "moat": "🟢 Cost advantage in Permian (WTI <$70 profitable); $254B equity base supports longevity",
  "cycle_phase": "Capital Return",
  "financial_health": "Net debt/EBITDA 0.39x, FCF margin 12%, interest coverage 69x — fortress balance sheet",
  "valuation": "Fair at 12x P/FCF vs sector 14x; dividend yield 3.01% above sector 2.8%",
  "risks": "Capex inflation eroding project economics | Texas redomicile governance noise | Q1 2026 net income -42% YoY"
}
</example>
"""


def _format_fundamentals(fundamentals: dict[str, Any] | None) -> str:
    if not fundamentals:
        return ""
    lines: list[str] = []
    for name, value in fundamentals.items():
        if value is None:
            lines.append(f"- {name}: n/a")
        elif isinstance(value, float):
            pct = abs(value) < 1.0
            if pct:
                lines.append(f"- {name}: {value * 100:.1f}%")
            else:
                lines.append(f"- {name}: {value:.2f}")
        else:
            lines.append(f"- {name}: {value}")
    return "\n".join(lines)


def _placeholder_summary(provider_name: str | None = None) -> WatchSummary:
    return WatchSummary(
        moat=_PLACEHOLDER_MOAT,
        cycle_phase=CyclePhase.CAPITAL_RETURN,
        financial_health="Data unavailable for financial health assessment",
        valuation="Data unavailable for valuation assessment",
        risks=_PLACEHOLDER_RISKS,
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
    fundamentals: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    truncated = _truncate(debate_text, _MAX_DEBATE_CHARS)
    fundamentals_block = _format_fundamentals(fundamentals)
    fundamentals_section = (
        f"\n# Fundamentals snapshot (from data/cache/)\n{fundamentals_block}\n"
        if fundamentals_block
        else ""
    )
    system = (
        "You are a surveillance analyst. Read the debate transcript below and "
        "produce a structured 5-bullet summary that captures the company's "
        "investment posture. Each bullet must be grounded, concrete, and fit "
        "the character caps (≤200 chars, risks ≤400). "
        "cycle_phase MUST be exactly one of: Hyper-Growth | Operating Leverage | "
        "Capital Return | Decline. "
        "moat MUST start with exactly one emoji: "
        "🟢 (strong/widening) | 🟡 (moderate/stable) | 🔴 (weak/narrowing).\n\n"
        f"{_DO_NOT_BLOCK}\n"
        f"{_EXAMPLE_BLOCK}"
    )
    if repair:
        system += (
            "\n\nIMPORTANT — repair mode. Your previous attempt failed validation. "
            "Return all five fields, each a non-empty string. Keep the character caps "
            "and the required emoji on moat. Use only the allowed cycle_phase values."
        )
    user = (
        f"# Target\n- Ticker: {ticker}\n- Sector: {sector}\n"
        f"{fundamentals_section}\n"
        f"# Debate transcript\n{truncated}\n\n"
        f"# Required JSON fields\n"
        f"- moat: starts with 🟢/🟡/🔴; the company's competitive advantage, 1-2 short sentences with 1 specific data point\n"
        f"- cycle_phase: EXACTLY one of: Hyper-Growth | Operating Leverage | Capital Return | Decline\n"
        f"- financial_health: balance sheet + FCF + leverage in 1 sentence grounded in numbers\n"
        f"- valuation: cheap / fair / rich vs sector, with a specific multiple or anchor\n"
        f"- risks: 1-3 most concrete risks discussed, separated by ' | '\n"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def aggregate_one(
    provider_name: str,
    debate_ref: DebateRef,
    ticker: str,
    sector: str,
    *,
    fundamentals: dict[str, Any] | None = None,
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

    msgs = _build_messages(ticker, sector, debate_text, repair=False, fundamentals=fundamentals)
    result = _invoke_with_fallback(provider, WatchSummary, msgs)

    if result is None or not isinstance(result, WatchSummary):
        log.warning(
            "watch.aggregate.repair_attempt",
            ticker=ticker,
            sector=sector,
            provider=provider_name,
        )
        repair_msgs = _build_messages(
            ticker, sector, debate_text, repair=True, fundamentals=fundamentals
        )
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


__all__ = ["CyclePhase", "WatchSummary", "aggregate_one"]
