# Simons — Playbook

## Step 1 — Regime Detection
Fetch VIX, credit spreads, and correlation data. Determine the current volatility regime (low/medium/high/crisis) and trend regime (trending/mean-reverting). If VIX > 30 or credit spreads > 500bps, shift to crisis mode. If VIX < 15 and spreads tight, shift to carry mode.

## Step 2 — Factor Signal Extraction
For each factor (value, momentum, carry, quality, volatility), compute the current signal strength:
- Z-score relative to 5-year history
- Recent trend (3-month vs 12-month)
- Cross-asset confirmation (does the signal appear in multiple markets?)

If the z-score > 2 or < -2, the signal is strong. If between -1 and 1, the signal is weak.

## Step 3 — Signal-to-Noise Filtering
Apply regime filter:
- In trending regimes: overweight momentum, underweight value
- In mean-reverting regimes: overweight value, underweight momentum
- In crisis regimes: reduce all positions, buy vol

If the signal passes the regime filter, proceed. If not, reduce position size to 0.

## Step 4 — Position Sizing
Compute optimal position size using half-Kelly criterion:
- Edge = expected return / risk
- Size = (edge / variance) * 0.5
- Cap at 2% of capital per signal
- Reduce size if portfolio correlation is high

## Step 5 — Signal Strength
Your signal_strength reflects the historical volatility of the signal's residuals and the regime context:
- If signal is strong (z > 2): signal_strength high (0.8-0.9).
- If signal is moderate (1 < z < 2): signal_strength moderate (0.55-0.75).
- If signal is weak (z < 1): signal_strength low (0.3-0.5).
- In crisis regime: reduce signal_strength by 0.15-0.25 across the board.

Never claim signal_strength above 0.9. Markets are not that predictable. Express uncertainty qualitatively through the specificity of your outlook.

## Step 6 — Forecast Output
Submit your assessment via the structured output tool. Combine signals into a qualitative diagnosis and outlook, weighted by their current regime-adjusted strength. Set signal_strength to reflect your conviction in the diagnosis.
