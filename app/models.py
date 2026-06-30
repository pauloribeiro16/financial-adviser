from datetime import date
from enum import StrEnum

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
