from __future__ import annotations

from app.logging import get_logger

log = get_logger(__name__)

_MIN_MOAT = 1
_MAX_MOAT = 5
_MID_MOAT = 3
_BASE_MARGIN = 0.85
_MARGIN_STEP = 0.03
_DEEP_VALUE_MULTIPLIER = 1.5
_CHEAPISH_MULTIPLIER = 0.7


def _clamp_moat(value: int) -> int:
    if value < _MIN_MOAT:
        return _MIN_MOAT
    if value > _MAX_MOAT:
        return _MAX_MOAT
    return value


def _safe_nonneg(value: float, default: float = 0.0) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if v != v:
        return default
    return v


def moat_strength_from_text(moat_bullet: str) -> int:
    """Map an aggregator's moat bullet to an integer 1..5.

    Heuristic priority (first match wins):
        5 — 3 green dots, "widening", "deepening", score keywords like "4-5" or "score 5"
        4 — single green dot, "narrowing+strength", "stable moat"
        3 — yellow dot, "moderate"
        2 — red dot, "eroding", "shrinking"
        1 — absent, "none", "no moat", "commodity"
    """
    if not moat_bullet:
        return 1
    text = moat_bullet.strip().lower()
    if not text:
        return 1

    if "🟢🟢🟢" in moat_bullet:
        return 5
    green_count = moat_bullet.count("🟢")
    red_count = moat_bullet.count("🔴")
    yellow_count = moat_bullet.count("🟡")

    if any(kw in text for kw in ("widening", "deepening", "expanding")):
        return 5
    if any(kw in text for kw in ("score 5", "4-5", "score: 5", "(5/5)")):
        return 5

    if any(kw in text for kw in ("eroding", "shrinking", "vanishing", "destroyed")):
        return 2
    if any(kw in text for kw in ("no moat", "commodity", "absent")):
        return 1

    if green_count >= 2:
        return 4
    if red_count >= 2 or (red_count >= 1 and green_count == 0):
        return 2
    if yellow_count >= 1 and green_count == 0 and red_count == 0:
        return 3

    if "🟢" in moat_bullet:
        return 4
    if "🟡" in moat_bullet:
        return 3
    if "🔴" in moat_bullet:
        return 2

    if any(kw in text for kw in ("stable moat", "persistent moat", "narrow moat")):
        return 4
    if "moderate" in text:
        return 3
    if "weak" in text or "thin" in text:
        return 2

    return 3


def compute_buy_price(
    current_price: float,
    sector_target_fcf_yield: float,
    company_fcf_yield: float,
    moat_strength: int,
) -> float:
    """Heuristic buy price = fair_value * margin.

        fair_value = current_price * (company_fcf_yield / sector_target_fcf_yield)
        margin    = 0.85 + 0.03 * (moat_strength - 3)   # 0.79 (moat=1) to 0.91 (moat=5)

    Interpretation:
        - company FCF yield above sector → cheap vs peers → fair_value > current → buy_price > current
        - company FCF yield below sector → rich vs peers → fair_value < current → buy_price < current
        - moat_strength widens the margin (less discount when moat is strong).

    Edge cases:
        - company_fcf_yield <= 0   → return current_price * 1.5
            (deep value trap escape; do not try to invert a non-positive yield)
        - sector_target_fcf_yield <= 0 → return current_price * 0.7
            (cheap-ish default; sector reference is broken)

    Negative current_price / non-finite moat_strength are clamped:
        - moat_strength outside [1, 5] is clamped into range
    """
    moat = _clamp_moat(int(moat_strength))

    current = _safe_nonneg(current_price, default=0.0)
    sector_yield = _safe_nonneg(sector_target_fcf_yield, default=0.0)
    company_yield = _safe_nonneg(company_fcf_yield, default=0.0)

    log.debug(
        "watch.price_target.compute",
        current_price=current,
        sector_yield=sector_yield,
        company_yield=company_yield,
        moat_strength=moat,
    )

    if company_yield <= 0:
        return current * _DEEP_VALUE_MULTIPLIER
    if sector_yield <= 0:
        return current * _CHEAPISH_MULTIPLIER

    fair_value = current * (company_yield / sector_yield)
    margin = _BASE_MARGIN + _MARGIN_STEP * (moat - _MID_MOAT)
    return fair_value * margin
