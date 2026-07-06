"""3-call LLM summarization of 10-K sections with map-reduce."""

from __future__ import annotations

import time

import httpx

from app.filings import cache, prompts
from app.filings.fetcher import download_10k_html
from app.filings.section_parser import extract_sections
from app.logging import get_logger
from app.models import FilingSummary
from app.pipeline.edgar import cik_for_ticker, latest_10k_accession
from app.providers import ProviderRegistry

log = get_logger(__name__)

_MAX_WORDS_DIRECT = 8000
_CHUNK_WORDS = 4000
_CHUNK_OVERLAP = 200
_MAX_CHARS = 18000
_MAX_RETRIES = 2
_RETRY_BACKOFF_S = 2.0


def _word_count(text: str) -> int:
    return len(text.split())


def _chunk_text(text: str, chunk_words: int, overlap_words: int) -> list[str]:
    words = text.split()
    if len(words) <= chunk_words:
        return [text]
    chunks: list[str] = []
    step = max(1, chunk_words - overlap_words)
    for i in range(0, len(words), step):
        slice_words = words[i : i + chunk_words]
        if not slice_words:
            break
        chunks.append(" ".join(slice_words))
        if i + chunk_words >= len(words):
            break
    return chunks


def _truncate(s: str, n: int) -> str:
    if len(s) <= n:
        return s
    return s[:n] + "…"


def _extract_text(response: object) -> str:
    """Robustly extract text content from various response shapes."""
    if response is None:
        return ""
    if isinstance(response, str):
        return response.strip()
    content = getattr(response, "content", None)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                t = block.get("text")
                if isinstance(t, str):
                    parts.append(t)
        return "\n".join(parts).strip()
    text_attr = getattr(response, "text", None)
    if isinstance(text_attr, str):
        return text_attr.strip()
    return str(response).strip()


def _call_llm(provider, system_prompt: str, *, ticker: str, label: str) -> str:
    """One free-text LLM call with retry. Returns the assistant content."""
    msgs = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Summarize the section above."},
    ]
    last_err: str | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            model = provider.get_model()
            response = model.invoke(msgs)
            text = _extract_text(response)
            if text and not text.startswith("{"):
                log.info(
                    "filings.summarize.done",
                    ticker=ticker, label=label,
                    attempt=attempt, chars=len(text),
                )
                return text[:1500] if len(text) > 1500 else text
            last_err = f"empty or JSON-shaped text: {text[:80]!r}"
            log.warning(
                "filings.summarize.bad_response",
                ticker=ticker, label=label, attempt=attempt,
                preview=text[:120],
            )
        except Exception as e:
            last_err = str(e)[:200]
            log.warning(
                "filings.summarize.attempt_failed",
                ticker=ticker, label=label, attempt=attempt, error=last_err,
            )
        if attempt < _MAX_RETRIES:
            time.sleep(_RETRY_BACKOFF_S * attempt)
    log.error(
        "filings.summarize.gave_up",
        ticker=ticker, label=label, error=last_err,
    )
    return ""


def _summarize_section(
    provider, text: str, template: str, *, ticker: str, label: str,
) -> str:
    """Map-reduce: single call if <=8K words, else chunk + consolidate."""
    if _word_count(text) <= _MAX_WORDS_DIRECT:
        return _call_llm(provider, _truncate(template.format(text=text), _MAX_CHARS), ticker=ticker, label=label)
    log.info("filings.map_reduce", ticker=ticker, section=label, words=_word_count(text))
    chunks = _chunk_text(text, _CHUNK_WORDS, _CHUNK_OVERLAP)
    partials: list[str] = []
    for ch in chunks:
        s = _call_llm(provider, _truncate(template.format(text=ch), _MAX_CHARS), ticker=ticker, label=label)
        if s:
            partials.append(s)
    if not partials:
        return ""
    if len(partials) == 1:
        return partials[0]
    joined = "\n\n".join(f"[{i + 1}] {p}" for i, p in enumerate(partials))
    consolidated_prompt = prompts.CONSOLIDATION_PROMPT.format(n=len(partials), partials=_truncate(joined, _MAX_CHARS))
    consolidated = _call_llm(
        provider, consolidated_prompt, ticker=ticker, label=f"{label}_consolidate",
    )
    return consolidated or " ".join(partials)


def summarize_sections(
    sections: dict[str, str], ticker: str, provider_name: str,
) -> FilingSummary:
    """Summarize the 3 grouped sections into a FilingSummary (3 calls)."""
    provider = ProviderRegistry.get(provider_name)
    business_and_market_risk = _summarize_section(
        provider,
        (sections.get("business", "") + "\n\n" + sections.get("market_risk", "")).strip(),
        prompts.SECTION_PROMPT_BUSINESS_RISK,
        ticker=ticker, label="business_market_risk",
    )
    risk_factors = _summarize_section(
        provider,
        sections.get("risk_factors", ""),
        prompts.SECTION_PROMPT_RISK_FACTORS,
        ticker=ticker, label="risk_factors",
    )
    md_and_a = _summarize_section(
        provider,
        sections.get("md_and_a", ""),
        prompts.SECTION_PROMPT_MD_A,
        ticker=ticker, label="md_and_a",
    )
    return FilingSummary(
        ticker=ticker,
        filing_date="",
        form="10-K",
        business_and_market_risk=business_and_market_risk,
        risk_factors=risk_factors,
        md_and_a=md_and_a,
    )


def get_or_build_summary(ticker: str, provider_name: str) -> FilingSummary | None:
    """Cache-first. On miss: download 10-K + parse + summarize + cache."""
    cached_date = cache.latest_filing_date(ticker)
    if cached_date:
        cached = cache.get(ticker, cached_date)
        if cached is not None:
            log.info("filings.cache_hit", ticker=ticker, filing_date=cached_date)
            return cached
    cik = cik_for_ticker(ticker)
    if not cik:
        log.warning("filings.no_cik", ticker=ticker)
        return None
    ten_k_info = latest_10k_accession(cik)
    if not ten_k_info:
        log.warning("filings.no_10k", ticker=ticker)
        return None
    try:
        html = download_10k_html(cik, ten_k_info["accession"], ten_k_info["primary_document"])
    except httpx.HTTPError as e:
        log.warning("filings.download_failed", ticker=ticker, error=str(e))
        return None
    sections = extract_sections(html)
    summary = summarize_sections(sections, ticker, provider_name)
    summary.filing_date = ten_k_info["filing_date"]
    cache.put(summary)
    log.info("filings.summary_built", ticker=ticker, filing_date=summary.filing_date)
    return summary


__all__ = ["get_or_build_summary", "summarize_sections"]
