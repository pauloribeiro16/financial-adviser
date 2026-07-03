from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from app.logging import get_logger

log = get_logger(__name__)

_SECTORS_DIR = Path(__file__).resolve().parent

HealthierIs = Literal["higher", "lower", "mid"]


class IndicatorSpec(BaseModel):
    id: str
    name: str
    extract: str
    healthier_is: HealthierIs
    healthy_threshold: float
    warning_threshold: float
    unit: str | None = None

    @field_validator("id")
    @classmethod
    def _id_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("IndicatorSpec.id must be non-empty")
        return v

    @field_validator("extract")
    @classmethod
    def _extract_dotted(cls, v: str) -> str:
        if not v or "." not in v:
            raise ValueError(
                f"IndicatorSpec.extract must be a dotted path (got {v!r}); "
                "e.g. 'fundamentals.fcf_yield'"
            )
        return v

    @model_validator(mode="after")
    def _validate_thresholds(self) -> IndicatorSpec:
        if self.healthier_is == "lower":
            if self.healthy_threshold > self.warning_threshold:
                raise ValueError(
                    f"IndicatorSpec[{self.id}]: healthier_is='lower' requires "
                    f"healthy_threshold ({self.healthy_threshold}) <= "
                    f"warning_threshold ({self.warning_threshold})"
                )
        else:
            if self.healthy_threshold < self.warning_threshold:
                raise ValueError(
                    f"IndicatorSpec[{self.id}]: healthier_is='{self.healthier_is}' "
                    f"requires healthy_threshold ({self.healthy_threshold}) >= "
                    f"warning_threshold ({self.warning_threshold})"
                )
        return self


class _SectorFile(BaseModel):
    sector: str
    indicators: list[IndicatorSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def _non_empty(self) -> _SectorFile:
        if not self.indicators:
            raise ValueError(f"Sector '{self.sector}' has no indicators")
        return self


def _slug(name: str) -> str:
    return name.strip().lower().replace(" ", "-")


def _yaml_path(slug: str) -> Path:
    return _SECTORS_DIR / f"{slug}.yaml"


def _parse_yaml(path: Path) -> _SectorFile:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name}: top-level must be a mapping, got {type(raw).__name__}")
    return _SectorFile.model_validate(raw)


SECTOR_INDICATORS: dict[str, list[IndicatorSpec]] = {}


def _discover() -> None:
    if SECTOR_INDICATORS:
        return
    for path in sorted(_SECTORS_DIR.glob("*.yaml")):
        slug = path.stem
        try:
            parsed = _parse_yaml(path)
        except Exception as e:
            log.error("sectors.load_failed", path=str(path), error=str(e))
            raise
        SECTOR_INDICATORS[slug] = parsed.indicators
        log.info("sectors.loaded", sector=slug, n_indicators=len(parsed.indicators))


_discover()


def available_sectors() -> list[str]:
    return sorted(SECTOR_INDICATORS.keys())


def load_sector(name: str) -> list[IndicatorSpec]:
    slug = _slug(name)
    if slug not in SECTOR_INDICATORS:
        raise FileNotFoundError(
            f"Unknown sector {name!r} (slug={slug!r}). "
            f"Available: {available_sectors()}"
        )
    return list(SECTOR_INDICATORS[slug])


def slug_for(name: str) -> str:
    return _slug(name)
