from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import app.sectors as sectors_mod
from app.sectors import (
    SECTOR_INDICATORS,
    IndicatorSpec,
    available_sectors,
    load_sector,
    slug_for,
)

EXPECTED_SLUGS = {"energy", "technology", "healthcare", "financial-services"}
SECTORS_DIR = Path(sectors_mod.__file__).resolve().parent


def test_available_sectors_has_four_entries() -> None:
    slugs = available_sectors()
    assert len(slugs) == 4
    assert set(slugs) == EXPECTED_SLUGS


def test_sector_indicators_dict_has_four_keys() -> None:
    assert set(SECTOR_INDICATORS.keys()) == EXPECTED_SLUGS


def test_every_sector_loads_at_least_six_indicators() -> None:
    for slug in EXPECTED_SLUGS:
        inds = load_sector(slug)
        assert len(inds) >= 6, f"{slug} has only {len(inds)} indicators"


@pytest.mark.parametrize("slug", sorted(EXPECTED_SLUGS))
def test_each_yaml_file_exists_and_parses(slug: str) -> None:
    path = SECTORS_DIR / f"{slug}.yaml"
    assert path.is_file(), f"missing YAML for {slug}"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    assert "indicators" in raw
    assert isinstance(raw["indicators"], list)
    assert len(raw["indicators"]) >= 6


def test_load_sector_returns_indicator_spec_instances() -> None:
    inds = load_sector("energy")
    assert all(isinstance(i, IndicatorSpec) for i in inds)


def test_load_sector_accepts_human_name_with_spaces() -> None:
    inds = load_sector("Financial Services")
    assert inds == load_sector("financial-services")
    assert inds == SECTOR_INDICATORS["financial-services"]


def test_load_sector_unknown_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_sector("nonexistent-sector")


def test_indicator_spec_extract_must_be_dotted() -> None:
    with pytest.raises(ValueError):
        IndicatorSpec(
            id="bad",
            name="Bad",
            extract="no_dot",
            healthier_is="higher",
            healthy_threshold=1.0,
            warning_threshold=0.0,
        )


def test_indicator_spec_id_must_be_non_empty() -> None:
    with pytest.raises(ValueError):
        IndicatorSpec(
            id="   ",
            name="Bad",
            extract="a.b",
            healthier_is="higher",
            healthy_threshold=1.0,
            warning_threshold=0.0,
        )


def test_indicator_spec_lower_requires_healthy_le_warning() -> None:
    with pytest.raises(ValueError):
        IndicatorSpec(
            id="bad_lower",
            name="Bad Lower",
            extract="a.b",
            healthier_is="lower",
            healthy_threshold=5.0,
            warning_threshold=2.0,
        )


def test_indicator_spec_higher_requires_healthy_ge_warning() -> None:
    with pytest.raises(ValueError):
        IndicatorSpec(
            id="bad_higher",
            name="Bad Higher",
            extract="a.b",
            healthier_is="higher",
            healthy_threshold=-1.0,
            warning_threshold=0.0,
        )


def test_indicator_spec_accepts_valid_lower_thresholds() -> None:
    spec = IndicatorSpec(
        id="good_lower",
        name="Good Lower",
        extract="a.b",
        healthier_is="lower",
        healthy_threshold=1.5,
        warning_threshold=2.5,
    )
    assert spec.healthier_is == "lower"


def test_indicator_spec_accepts_valid_higher_thresholds() -> None:
    spec = IndicatorSpec(
        id="good_higher",
        name="Good Higher",
        extract="a.b",
        healthier_is="higher",
        healthy_threshold=0.0,
        warning_threshold=-0.15,
    )
    assert spec.healthier_is == "higher"


def test_indicator_spec_accepts_mid_thresholds() -> None:
    spec = IndicatorSpec(
        id="good_mid",
        name="Good Mid",
        extract="a.b",
        healthier_is="mid",
        healthy_threshold=0.03,
        warning_threshold=0.015,
    )
    assert spec.healthier_is == "mid"


def test_indicator_ids_unique_within_each_sector() -> None:
    for slug in EXPECTED_SLUGS:
        inds = load_sector(slug)
        ids = [i.id for i in inds]
        assert len(ids) == len(set(ids)), f"duplicates in {slug}: {ids}"


def test_every_indicator_has_required_fields() -> None:
    for slug in EXPECTED_SLUGS:
        for spec in load_sector(slug):
            assert spec.id
            assert spec.name
            assert "." in spec.extract
            assert spec.healthier_is in {"higher", "lower", "mid"}
            assert isinstance(spec.healthy_threshold, float)
            assert isinstance(spec.warning_threshold, float)


def test_slug_for_lowercases_and_dashes() -> None:
    assert slug_for("Energy") == "energy"
    assert slug_for("Financial Services") == "financial-services"
    assert slug_for("  Healthcare  ") == "healthcare"


def test_energy_yaml_matches_contract() -> None:
    raw = yaml.safe_load((SECTORS_DIR / "energy.yaml").read_text(encoding="utf-8"))
    ids = {i["id"] for i in raw["indicators"]}
    assert {"wti_yoy", "fcf_yield", "net_debt_ebitda", "capex_revenue",
            "dividend_yield", "share_count_yoy"} <= ids
