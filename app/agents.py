"""Multi-persona macroeconomic assessment (LangChain + Langfuse, no DB).

The pipeline per (persona, indicator):
  1. build system prompt from `app/prompts/<persona>/{PERSONA.md, references/*.md, indicators/_index.md}`
  2. build user prompt with optional `indicators/<id>.md` deep note + per-persona hint
  3. call LLM via `model.with_structured_output(Assessment)` (Pydantic)
  4. on failure, fall back to plain invoke + JSON-parse

Run end-to-end: `python -m app.main --analysts buffett,burry --mock`
Or import:
    from app.agents import ALL_AGENTS
    from app.runner import run
    results = run(["buffett", "burry"], provider_name="mock")
"""

from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from app.logging import get_logger
from app.models import AgentProfile, Assessment
from app.providers import LLMProvider, ProviderRegistry

log = get_logger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"
_SEPARATOR = "\n\n---\n\n"

__all__ = [
    "ALL_AGENTS",
    "Assessment",
    "AgentProfile",
    "BaseAgent",
    "build_indicator_context",
    "build_system_prompt",
    "build_user_prompt",
]  # noqa: F822  (re-export Assessment/AgentProfile from app.models)


# ---- Per-persona hint table (3 slots: related + remember + style) ----

@dataclass(frozen=True)
class _Hint:
    related: str
    remember: str


_HINTS: dict[str, _Hint] = {
    "buffett":   _Hint("equity, earnings, valuation",        "Focus on intrinsic value, moats, long-term compounding. Skeptical of short-term noise."),
    "lynch":     _Hint("earnings, consumer, growth",         "Find the story. Check the PEG. Look for tenbaggers. Keep it simple."),
    "dalio":     _Hint("credit, monetary, cycle",            "Think in cycles — debt, productivity, paradigm shifts. Be systematic."),
    "burry":     _Hint("valuation, credit, monetary",        "Look for disconnects between price and value. Be skeptical of consensus."),
    "greenspan": _Hint("productivity, inflation, labor",     "Be data-dependent, nuanced, and forward-looking. Reference productivity trends."),
    "bernanke":  _Hint("credit, monetary, financial",        "Learn from history. Don't repeat the mistakes of the 1930s. Be decisive in crisis."),
    "volcker":   _Hint("inflation, monetary, wage",          "Inflation is the enemy. Be principled. Do what is right, not what is popular."),
    "dimon":     _Hint("employment, credit, consumer",       "Check the consumer first. Stress the credit cycle. Scan for storm clouds."),
    "eisman":    _Hint("credit, employment, housing",        "Read the footnotes. Check credit spreads. Complexity is camouflage."),
    "grantham":  _Hint("valuation, credit, commodity",       "Mean reversion always wins. CAPE does not lie. Be prepared to be early."),
    "simons":    _Hint("factor, volatility, regime",          "Think in z-scores, not narratives. The model decides. Signal strength = position size."),
    "taleb":     _Hint("volatility, credit, risk",           "Do not predict — position. Fat tails, barbell, optionality. Distribution is fatter than you think."),
    "wood":      _Hint("innovation, technology, growth",     "Innovation is the solution, not the problem. Deflation from technology is coming."),
    "gundlach":  _Hint("yield curve, credit, monetary",       "The bond market is the truth-teller. The curve leads everything."),
    "thaler":    _Hint("sentiment, confidence, behavioral",   "Markets are not efficient because people are not rational. Find the biases."),
}

_USER_TEMPLATE = """You are assessing {indicator_id} for the period ending {target_date}.
{note_block}Related-indicator categories: {related}.

Submit a single assessment with these fields:
- diagnosis: 1-2 sentence current state of {indicator_id}.
- outlook: 1-2 sentence directional view, qualitative, ~1Q-1Y. No numeric targets.
- key_drivers: 3-5 bullets — indicators or news driving the call.
- news_interpretation: how recent headlines shaped the view (or "no material news").
- reasoning_trace: 2-4 paragraph walkthrough.
- signal_direction: BULLISH | BEARISH | NEUTRAL.
- signal_strength: float 0.0-1.0 (your conviction).

{remember}"""


# ---- Progressive disclosure loaders ----

def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def build_system_prompt(persona_id: str) -> str:
    pdir = PROMPTS_DIR / persona_id
    refs_dir = pdir / "references"
    parts = [
        _read(pdir / "PERSONA.md"),
        _SEPARATOR.join(sorted(_read(f) for f in refs_dir.glob("*.md")) if refs_dir.exists() else []),
        _read(pdir / "indicators" / "_index.md"),
    ]
    return _SEPARATOR.join(t for t in parts if t)


def build_indicator_context(persona_id: str, indicator_id: str) -> str:
    return _read(PROMPTS_DIR / persona_id / "indicators" / f"{indicator_id}.md")


def build_user_prompt(persona_id: str, indicator_id: str, target_date: date) -> str:
    note = build_indicator_context(persona_id, indicator_id)
    note_block = (
        f"\n=== DEEP KNOWLEDGE: {indicator_id} ===\n{note}\n=== END ===\n"
        if note
        else ""
    )
    hint = _HINTS[persona_id]
    return _USER_TEMPLATE.format(
        indicator_id=indicator_id,
        target_date=target_date.strftime("%Y-%m-%d"),
        note_block=note_block,
        related=hint.related,
        remember=hint.remember,
    )


# ---- Langfuse (optional) ----

def _make_langfuse_handler() -> Any | None:
    if not os.getenv("LANGFUSE_PUBLIC_KEY"):
        return None
    try:
        from langfuse.langchain import CallbackHandler

        return CallbackHandler()
    except Exception as e:
        log.warning("agent.langfuse_unavailable", error=str(e))
        return None


def _has_structured_output(model: Any) -> bool:
    return hasattr(model, "with_structured_output") and callable(model.with_structured_output)


# ---- BaseAgent ----

class BaseAgent(ABC):
    """Single (persona, indicator) LLM call. Subclasses set `agent_id`."""

    agent_id: str = ""

    def __init__(
        self,
        provider_name: str = "minimax",
        langfuse_handler: Any | None = None,
        indicator_meta: dict[str, dict[str, str]] | None = None,
    ):
        if not self.agent_id:
            raise ValueError(f"{type(self).__name__} must set agent_id")
        self.agent_id = self.agent_id
        self.provider_name = provider_name
        self.provider: LLMProvider = ProviderRegistry.get(provider_name)
        self.langfuse_handler = langfuse_handler if langfuse_handler is not None else _make_langfuse_handler()
        self._init_error: str | None = None
        self._model: Any | None = None
        self._structured: Any | None = None
        try:
            self._model = self.provider.get_model()
            self._structured = (
                self._model.with_structured_output(Assessment)
                if _has_structured_output(self._model)
                else None
            )
        except Exception as e:
            self._init_error = str(e)
            log.warning("agent.init_failed", agent_id=self.agent_id, error=self._init_error)
            return
        log.info("agent.initialized", agent_id=self.agent_id, provider=provider_name)

    def _invoke_config(self, indicator_id: str) -> dict:
        cfg: dict[str, Any] = {"metadata": {"langfuse_tags": [f"agent:{self.agent_id}", f"indicator:{indicator_id}"]}}
        if self.langfuse_handler is not None:
            cfg["callbacks"] = [self.langfuse_handler]
        return cfg

    def _post(self, raw: Any, indicator_id: str, target_date: date) -> Assessment:
        d = _to_dict(raw)
        return Assessment(
            agent_id=self.agent_id,
            indicator_id=indicator_id,
            target_date=target_date,
            provider=self.provider.provider_name(),
            diagnosis=str(d.get("diagnosis", "") or ""),
            outlook=str(d.get("outlook", "") or ""),
            key_drivers=list(d.get("key_drivers") or []),
            news_interpretation=str(d.get("news_interpretation", "") or ""),
            reasoning_trace=str(d.get("reasoning_trace", "") or ""),
            signal_direction=str(d.get("signal_direction", "NEUTRAL") or "NEUTRAL"),
            signal_strength=_clamp(d.get("signal_strength", 0.0)),
        )

    def generate_assessment(self, indicator_id: str, target_date: date) -> Assessment:
        if self._init_error is not None or self._model is None:
            raise RuntimeError(self._init_error or "agent model not initialized")
        messages = [
            {"role": "system", "content": self.get_system_prompt()},
            {"role": "user", "content": self.get_user_prompt(indicator_id, target_date)},
        ]
        cfg = self._invoke_config(indicator_id)
        if self._structured is not None:
            try:
                raw = self._structured.invoke(messages, config=cfg)
                return self._post(raw, indicator_id, target_date)
            except Exception as e:
                log.warning("agent.structured_failed_falling_back", agent_id=self.agent_id, error=str(e))
        response = self._model.invoke(messages, config=cfg)
        d = _parse_json_or_default(_extract_content(response))
        return self._post(d, indicator_id, target_date)

    @abstractmethod
    def get_profile(self) -> AgentProfile: ...

    @abstractmethod
    def get_system_prompt(self) -> str: ...

    @abstractmethod
    def get_user_prompt(self, indicator_id: str, target_date: date) -> str: ...


# ---- Helpers (parsing) ----

def _to_dict(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    for attr in ("model_dump", "dict"):
        if hasattr(raw, attr):
            try:
                return getattr(raw, attr)()
            except Exception:
                pass
    out: dict[str, Any] = {}
    for k in ("diagnosis", "outlook", "key_drivers",
              "news_interpretation", "reasoning_trace",
              "signal_direction", "signal_strength"):
        if hasattr(raw, k):
            out[k] = getattr(raw, k)
    return out


def _extract_content(response: Any) -> str:
    if isinstance(response, str):
        return response
    return getattr(response, "content", "") or ""


def _parse_json_or_default(s: str) -> dict:
    s = s.strip()
    if not s:
        return {}
    try:
        d = json.loads(s)
        return d if isinstance(d, dict) else {}
    except Exception:
        pass
    m = re.search(r"\{.*\}", s, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return {}


def _clamp(x: Any) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, v))


# ---- Persona registry (factory + ALL_AGENTS) ----

_PERSONA_DEFS: list[tuple[str, str, str, str]] = [
    ("buffett",   "Warren E. Buffett",       "Value Investing",                "Buys wonderful businesses at fair prices; intrinsic value and durable moats."),
    ("lynch",     "Peter Lynch",             "GARP",                           "Growth at a reasonable price via PEG; hunts tenbaggers."),
    ("dalio",     "Ray Dalio",               "Global Macro",                   "Sees the economy as a machine driven by debt cycles and paradigm shifts."),
    ("burry",     "Michael Burry",           "Deep Value / Contrarian",        "Margin-of-safety investor; bubble detector and patient contrarian."),
    ("greenspan", "Alan Greenspan",          "Fed Maestro",                    "Data-dependent central banker; productivity optimist."),
    ("bernanke",  "Ben Bernanke",            "Crisis Central Banking",         "Great Depression scholar; QE pioneer."),
    ("volcker",   "Paul Volcker",            "Hard Money",                     "Defeated double-digit inflation with the Volcker shock."),
    ("dimon",     "Jamie Dimon",             "Fortress Balance Sheet",         "JPMorgan CEO; cautious optimist; scans for storm clouds."),
    ("eisman",    "Steve Eisman",            "Credit Forensics",               "The Big Short investor; reads footnotes."),
    ("grantham",  "Jeremy Grantham",         "Mean Reversion",                 "Bubble historian; predicted dot-com, housing, Everything Bubble."),
    ("simons",    "Jim Simons",              "Quantitative / Systematic",      "Renaissance founder; decodes markets through mathematics."),
    ("taleb",     "Nassim Nicholas Taleb",   "Tail Risk / Antifragile",        "Author of The Black Swan; positions for fat tails."),
    ("wood",      "Cathie Wood",             "Disruptive Innovation",          "ARK Invest founder; evangelist of exponential growth."),
    ("gundlach",  "Jeffrey Gundlach",        "Fixed Income / Bond King",       "DoubleLine founder; reads the curve like radar."),
    ("thaler",    "Richard Thaler",          "Behavioral Finance",             "Nobel laureate; studies cognitive biases in markets."),
]


def _make_agent_class(persona_id: str, name: str, school: str, description: str) -> type[BaseAgent]:
    """Build a thin BaseAgent subclass for one persona."""

    def get_profile(_self: BaseAgent) -> AgentProfile:
        return AgentProfile(id=persona_id, name=name, school=school, description=description)

    def get_system_prompt(_self: BaseAgent) -> str:
        return build_system_prompt(persona_id)

    def get_user_prompt(_self: BaseAgent, indicator_id: str, target_date: date) -> str:
        return build_user_prompt(persona_id, indicator_id, target_date)

    return type(
        f"{persona_id.title().replace('_', '')}Agent",
        (BaseAgent,),
        {
            "agent_id": persona_id,
            "get_profile": get_profile,
            "get_system_prompt": get_system_prompt,
            "get_user_prompt": get_user_prompt,
        },
    )


ALL_AGENTS: dict[str, type[BaseAgent]] = {
    pid: _make_agent_class(pid, name, school, desc)
    for pid, name, school, desc in _PERSONA_DEFS
}
