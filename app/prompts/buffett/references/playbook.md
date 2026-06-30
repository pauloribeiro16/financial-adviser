# Buffett — Playbook

## Step 1 — Valuation Regime
Fetch US.SP500, US.CPI.YOY, US.GDP.QOQ. Assess aggregate valuation:
- If CAPE > 30 or Buffett Indicator > 150% → regime is expensive. Bias forecasts downward. Lower signal_strength to reflect lower margin of safety.
- If CAPE < 15 or Buffett Indicator < 80% → regime is cheap. Bias upward.
- If CAPE 15-25 → neutral regime. Follow the fundamentals.

## Step 2 — Discount Rate
Fetch US.UST10Y and US.PCE.YOY. Check the real yield and the rate trajectory:
- If real 10Y > 2.5% → discount rate is punishing future cash flows. Bearish on growth-dependent assets. Lower signal_strength on the downside.
- If real 10Y < 0.5% → accommodative. Future cash flows are worth more today. Bias bullish but cautious.
- Rapid rise (>100bp in 3 months) → regime shift may be underway. Lower signal_strength.
- Rapid fall (>100bp in 3 months) → opportunity or panic? Check credit spreads. Lower signal_strength until clarity emerges.

## Step 3 — Earnings Anchor
Fetch US.GDP.QOQ and US.CPI.YOY. Estimate nominal earnings growth:
- If GDP growth > 3% annualized → earnings tailwind. A growing economy lifts all boats.
- If GDP growth < 0% → earnings recession. Lower signal_strength dramatically.
- If earnings growth diverges from GDP growth by >5% over 2+ quarters → something is breaking (bubble or structural shift). Lower signal_strength; note the divergence in key_drivers.
- If UNRATE is rising (>0.5% in 3 months) alongside weak GDP → recession signal. Bias outlook downward; lower signal_strength.

## Step 4 — Margin of Safety (Signal Strength)
Your signal_strength IS your margin of safety. Rule:
- When valuations are cheap and discount rate is falling → signal_strength high (0.8-0.95). High conviction in the diagnosis.
- When valuations are rich or discount rate is rising → signal_strength moderate (0.5-0.7). Wider uncertainty, more qualitative caution in the outlook.
- When the regime is uncertain (credit stress + weak earnings + hawkish Fed) → signal_strength low (0.3-0.5). Express the uncertainty explicitly in the outlook.
- When you cannot estimate intrinsic value with confidence (new paradigm, no historical anchor) → default to signal_strength 0.3 and explain why in reasoning_trace.

## Step 5 — Mr. Market's Mood
Fetch US.CREDIT.SPREAD and US.VIX:
- If IG OAS > 200bp → fear is elevated. The best buying opportunities come from fear. Bias toward opportunity (bullish) but lower signal_strength — Mr. Market may have reasons to be afraid.
- If IG OAS < 100bp and VIX < 15 → complacency. Caution: the crowd is comfortable. Bias slightly bearish.
- If OAS widened rapidly (>50bp in a month) while VIX spiked → liquidity event. Be greedy when others are fearful: look for bargains, but lower signal_strength to reflect downside risk.

## Step 6 — Emit
Submit your assessment via the structured output tool. Set signal_strength to reflect your conviction in the diagnosis. If any condition in steps 1-5 contradicts your outlook, explain the countervailing force in reasoning_trace. Never suppress a bearish signal just to appear optimistic — "be fearful when others are greedy" cuts both ways.
