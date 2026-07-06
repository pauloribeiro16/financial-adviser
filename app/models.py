from __future__ import annotations

import re
from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

_XML_TAG_RE = re.compile(r"<[^>]+>")


def _coerce_str_list(v: Any) -> list[str]:
    """Coerce any nested structure into a flat list of plain strings.

    Designed to absorb structured-output quirks where the LLM returns a
    ``list[list[str]]`` (each item wrapped in its own list) or wraps each
    string in XML-ish tags such as ``<item>...</item>``.

    Behaviour:
        - ``None`` -> ``[]``
        - scalars (str/int/float/bool) -> stripped XML-stripped str
        - list/tuple/set -> recursively flattened
        - elements that are neither list nor str are stringified
        - empty / whitespace-only strings are dropped
    """
    if v is None:
        return []
    out: list[str] = []

    def _flatten(x: Any) -> None:
        if isinstance(x, str):
            cleaned = _XML_TAG_RE.sub("", x).strip()
            if cleaned:
                out.append(cleaned)
        elif isinstance(x, (list, tuple, set)):
            for item in x:
                _flatten(item)
        else:
            cleaned = _XML_TAG_RE.sub("", str(x)).strip()
            if cleaned:
                out.append(cleaned)

    _flatten(v)
    return out


class Bloc(StrEnum):
    US = "US"


class Category(StrEnum):
    GROWTH = "GROWTH"
    INFLATION = "INFLATION"
    LABOR = "LABOR"
    MONETARY = "MONETARY"
    YIELDS = "YIELDS"
    CREDIT = "CREDIT"
    EQUITIES = "EQUITIES"
    SENTIMENT = "SENTIMENT"


class Frequency(StrEnum):
    D = "D"
    M = "M"
    Q = "Q"


class Transformation(StrEnum):
    LEVEL = "LEVEL"
    YOY = "YOY"
    QOQ = "QOQ"
    SPREAD = "SPREAD"


class Direction(StrEnum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


_DIRECTION_TOKENS: tuple[str, ...] = ("BULLISH", "BEARISH", "NEUTRAL")


def _coerce_direction(v: Any) -> str:
    """Extract BULLISH/BEARISH/NEUTRAL from a free-form string.

    MiniMax-M3 occasionally returns enum values as sentences such as
    ``"NEUTRAL with conviction 0.50"``. Pydantic's strict enum validator
    rejects those. We scan for the first matching token (case-insensitive);
    fall back to ``"NEUTRAL"`` when nothing is found.
    """
    if isinstance(v, str):
        upper = v.upper()
        for tok in _DIRECTION_TOKENS:
            if tok in upper:
                return tok
    if hasattr(v, "value"):
        return v.value
    return "NEUTRAL"


class Domain(StrEnum):
    COMPANY = "company"
    MACRO = "macro"


class Consensus(StrEnum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    SPLIT_BULL = "SPLIT_BULL"
    SPLIT_BEAR = "SPLIT_BEAR"
    NEUTRAL = "NEUTRAL"


class Indicator(BaseModel):
    indicator_id: str
    bloc: Bloc = Bloc.US
    category: Category
    name: str
    source: str
    source_series: str | None = None
    frequency: Frequency
    units: str | None = None
    transformation: Transformation = Transformation.LEVEL
    tier: int = 3


class Assessment(BaseModel):
    agent_id: str
    indicator_id: str
    target_date: date
    provider: str
    diagnosis: str
    outlook: str
    key_drivers: list[str] = Field(default_factory=list)
    news_interpretation: str = ""
    reasoning_trace: str = ""
    signal_direction: str
    signal_strength: float = Field(ge=0.0, le=1.0)

    @field_validator("key_drivers", mode="before")
    @classmethod
    def _coerce_lists(cls, v: Any) -> list[str]:
        return _coerce_str_list(v)


class AgentProfile(BaseModel):
    id: str
    name: str
    school: str
    description: str


class Thesis(BaseModel):
    agent_id: str
    target: str
    domain: Domain
    round: int
    verdict: Direction
    conviction: float = Field(ge=0.0, le=1.0)
    key_drivers: list[str] = Field(default_factory=list)
    reasoning: str
    data_used: list[str] = Field(default_factory=list)

    @field_validator("verdict", mode="before")
    @classmethod
    def _coerce_verdict(cls, v: Any) -> str:
        return _coerce_direction(v)

    @field_validator("key_drivers", "data_used", mode="before")
    @classmethod
    def _coerce_lists(cls, v: Any) -> list[str]:
        return _coerce_str_list(v)


class ThesisInput(BaseModel):
    """Schema sent to the LLM for thesis generation.

    Excludes ``agent_id``, ``target``, ``domain`` and ``round`` — those are
    stamped by the caller (``app.debate.engine._run_round_theses``) AFTER the
    LLM call. Slimming the tool schema from 7 required fields to 3
    dramatically improves MiniMax-M3 tool-call reliability.
    """

    verdict: Direction
    conviction: float = Field(ge=0.0, le=1.0)
    key_drivers: list[str] = Field(default_factory=list)
    reasoning: str
    data_used: list[str] = Field(default_factory=list)

    @field_validator("verdict", mode="before")
    @classmethod
    def _coerce_verdict(cls, v: Any) -> str:
        return _coerce_direction(v)

    @field_validator("key_drivers", "data_used", mode="before")
    @classmethod
    def _coerce_lists(cls, v: Any) -> list[str]:
        return _coerce_str_list(v)


class Rebuttal(BaseModel):
    agent_id: str
    target: str
    domain: Domain
    round: int
    targets: list[str] = Field(default_factory=list)
    concessions: list[str] = Field(default_factory=list)
    disagreements: list[str] = Field(default_factory=list)
    revised_verdict: Direction
    revised_conviction: float = Field(ge=0.0, le=1.0)
    reasoning: str

    @field_validator("revised_verdict", mode="before")
    @classmethod
    def _coerce_revised_verdict(cls, v: Any) -> str:
        return _coerce_direction(v)

    @field_validator("targets", "concessions", "disagreements", mode="before")
    @classmethod
    def _coerce_lists(cls, v: Any) -> list[str]:
        return _coerce_str_list(v)


class RebuttalInput(BaseModel):
    """Schema sent to the LLM for rebuttal generation.

    Excludes the same id-fields as ``ThesisInput``. Slim from 7 required to
    3 required so MiniMax-M3 tool calls succeed more reliably.
    """

    targets: list[str] = Field(default_factory=list)
    concessions: list[str] = Field(default_factory=list)
    disagreements: list[str] = Field(default_factory=list)
    revised_verdict: Direction
    revised_conviction: float = Field(ge=0.0, le=1.0)
    reasoning: str

    @field_validator("revised_verdict", mode="before")
    @classmethod
    def _coerce_revised_verdict(cls, v: Any) -> str:
        return _coerce_direction(v)

    @field_validator("targets", "concessions", "disagreements", mode="before")
    @classmethod
    def _coerce_lists(cls, v: Any) -> list[str]:
        return _coerce_str_list(v)


class Verdict(BaseModel):
    target: str
    domain: Domain
    consensus: Consensus
    bull_count: int
    bear_count: int
    neutral_count: int
    avg_conviction: float = Field(ge=0.0, le=1.0)
    points_of_agreement: list[str] = Field(default_factory=list)
    points_of_disagreement: list[str] = Field(default_factory=list)
    final_call: str
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str

    @field_validator("points_of_agreement", "points_of_disagreement", mode="before")
    @classmethod
    def _coerce_lists(cls, v: Any) -> list[str]:
        return _coerce_str_list(v)


class DebateResult(BaseModel):
    run_id: str
    domain: Domain
    target: str
    target_date: date
    provider: str
    analysts: list[str]
    context: dict[str, Any] = Field(default_factory=dict)
    theses: list[Thesis] = Field(default_factory=list)
    rebuttals: list[Rebuttal] = Field(default_factory=list)
    verdict: Verdict | None = None
    created_at: str

    @field_validator("analysts", mode="before")
    @classmethod
    def _coerce_lists(cls, v: Any) -> list[str]:
        return _coerce_str_list(v)


class FilingSummary(BaseModel):
    ticker: str
    filing_date: str
    form: str
    business_and_market_risk: str = Field(..., max_length=1500)
    risk_factors: str = Field(..., max_length=1500)
    md_and_a: str = Field(..., max_length=1500)

    @model_validator(mode="after")
    def _truncate_long_sections(self) -> FilingSummary:
        for field_name in ("business_and_market_risk", "risk_factors", "md_and_a"):
            value = getattr(self, field_name)
            if len(value) > 1500:
                setattr(self, field_name, value[:1497] + "…")
        return self
