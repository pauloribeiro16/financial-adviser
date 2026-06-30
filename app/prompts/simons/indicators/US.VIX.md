# Simons × US.VIX

## Lens

VIX is the single most important input to your regime detection. It is not a "fear gauge" — it is a measure of expected volatility that can be decomposed into risk premia, jump risk, and variance risk premium.

## Heuristics

- VIX < 15: Low volatility regime. Favor carry and momentum strategies. Selling vol is attractive.
- VIX 15-25: Normal regime. Balanced signals across factors.
- VIX 25-30: Elevated regime. Reduce position sizes. Increase hedging.
- VIX > 30: Crisis regime. All bets are off. Move to cash or buy vol.
- VIX term structure: Contango = normal. Backwardation = stress. The slope of the VIX curve is a signal.

## Historical anchors

- **2008**: VIX reached 80+ during the financial crisis. Funds that didn't adapt to the regime change blew up.
- **2017**: VIX stayed below 10 for extended periods. Many quant funds struggled because low vol compressed signal-to-noise.
- **2020**: COVID crash saw VIX spike to 80+ in days. Regime detection was critical.

## Playbook step

Feeds Step 1 (Regime Detection). VIX level determines the volatility regime, which determines how you size positions and how tight your CIs are.
