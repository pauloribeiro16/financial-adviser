from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


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
