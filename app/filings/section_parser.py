"""Extract Item 1, 1A, 7, 7A from a 10-K HTML via regex."""

from __future__ import annotations

import re

from app.logging import get_logger

log = get_logger(__name__)

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

_ITEM1_RE = re.compile(
    r"Item\s+1[\.\s]+Business", re.IGNORECASE
)
_ITEM1A_RE = re.compile(
    r"Item\s+1A[\.\s]+Risk\s+Factors", re.IGNORECASE
)
_ITEM7_RE = re.compile(
    r"Item\s+7[\.\s]+Management", re.IGNORECASE
)
_ITEM7A_RE = re.compile(
    r"Item\s+7A[\.\s]+Quantitative", re.IGNORECASE
)

_HEADERS = [
    ("business", _ITEM1_RE),
    ("risk_factors", _ITEM1A_RE),
    ("md_and_a", _ITEM7_RE),
    ("market_risk", _ITEM7A_RE),
]

_EMPTY: dict[str, str] = {
    "business": "",
    "risk_factors": "",
    "md_and_a": "",
    "market_risk": "",
}


def _strip_html(html: str) -> str:
    text = _HTML_TAG_RE.sub(" ", html)
    text = _WS_RE.sub(" ", text)
    return text.strip()


def _find_positions(text: str) -> dict[str, int]:
    """Find the byte position of each Item header in stripped text."""
    positions: dict[str, int] = {}
    for name, pat in _HEADERS:
        m = pat.search(text)
        if m:
            positions[name] = m.start()
    return positions


def extract_sections(html_text: str) -> dict[str, str]:
    """Extract 4 sections from a 10-K HTML.

    Returns dict with keys business, risk_factors, md_and_a, market_risk.
    Missing sections return empty string.
    """
    if not html_text:
        return dict(_EMPTY)
    text = _strip_html(html_text)
    positions = _find_positions(text)
    ordered = sorted(positions.items(), key=lambda kv: kv[1])
    out: dict[str, str] = dict(_EMPTY)
    for idx, (name, start) in enumerate(ordered):
        end = ordered[idx + 1][1] if idx + 1 < len(ordered) else len(text)
        chunk = text[start:end].strip()
        if len(chunk) > 50:
            out[name] = chunk
        else:
            log.warning("filings.section_too_short", section=name, length=len(chunk))
    return out
