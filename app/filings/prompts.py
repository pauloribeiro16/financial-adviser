"""Prompts for 10-K section summarization."""

from __future__ import annotations

SECTION_PROMPT_BUSINESS_RISK = """\
You are summarizing the BUSINESS and MARKET RISK disclosures of a 10-K filing.

Read the section text below and produce a structured summary (<=1400 chars) with:
- Company business segments and primary revenue drivers (1 short sentence)
- Competitive positioning or moat (1 sentence)
- Key market-risk exposures (FX, rates, commodities) (1 sentence)

Rules:
- Every claim must cite a specific data point or phrase from the text.
- No hedge language ("it appears", "might be").
- No padding. If a sub-area has no data, write "Not disclosed" -- never invent.
- Output the summary as plain prose, no markdown headers, no bullet points.

Section text:
{text}
"""

SECTION_PROMPT_RISK_FACTORS = """\
You are summarizing the RISK FACTORS section of a 10-K filing.

Read the text below and produce a structured summary (<=1400 chars) listing the TOP 5 RISKS,
ranked by materiality, separated by ' | '. For each risk: 1 short sentence with the specific exposure.

Rules:
- Use only risks stated explicitly in the text. No inventions.
- No hedge language. Rank by the text's own materiality.
- No padding. Output ONLY the ranked list, no headers.

Section text:
{text}
"""

SECTION_PROMPT_MD_A = """\
You are summarizing MANAGEMENT'S DISCUSSION AND ANALYSIS from a 10-K filing.

Read the text below and produce a structured summary (<=1400 chars) of:
- Results highlights (revenue, margins, YoY changes) (<=2 sentences, with specific numbers)
- Liquidity and capital allocation stance (1 sentence)
- Forward-looking statements or guidance (1 sentence, with caveat)

Rules:
- Cite specific numbers from the text. No inventions.
- No hedge language.
- For forward-looking statements, prefix with "Mgmt outlook:" so the reader knows it's guidance, not actuals.
- Output as plain prose, no markdown headers, no bullet points.

Section text:
{text}
"""

CONSOLIDATION_PROMPT = """\
You are consolidating {n} partial summaries into one coherent summary (<=500 chars).

Partial summaries:
{partials}

Produce ONE final summary <=500 chars that captures the union without redundancy. Use concise prose, no bullets. If two partials overlap, choose the most concrete phrasing. No hedge language.
"""

__all__ = [
    "CONSOLIDATION_PROMPT",
    "SECTION_PROMPT_BUSINESS_RISK",
    "SECTION_PROMPT_MD_A",
    "SECTION_PROMPT_RISK_FACTORS",
]
