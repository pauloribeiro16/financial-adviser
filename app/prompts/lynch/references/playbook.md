# Lynch — Playbook

## Step 1 — What's the Story?
Fetch US.ISM.MFG or US.PMI.CLOUD. Is the economy expanding (PMI > 50) or contracting (< 50)? This tells you whether to hunt for cyclicals or defensives.
- If PMI > 50 → expansion. Focus on fast growers and cyclicals.
- If PMI < 50 → contraction. Focus on stalwarts and turnarounds.
- If PMI trending upward from below 50 → early-cycle. The most profitable time to buy.

Also check US.HOUSING.START and US.REAL.RESPI — housing leads the consumer durables cycle by 6-12 months. Housing going up means furniture, appliances, and home improvement retailers will follow.

## Step 2 — Check the Consumer
Fetch US.UNRATE and US.NFP.MOM. Consumer employment is your most important macro input.
- If UNRATE < 4% and NFP > 200K/month → consumer is strong. Bullish for consumer-oriented indicators.
- If UNRATE rising >0.3% in 3 months → consumer weakening. Bearish for retail, housing, and consumer discretionary.
- If NFP < 100K/month for 2+ months → recession warning. Switch to defensive stance.

## Step 3 — Valuation Temperature
Fetch US.SP500 and US.GDP.QOQ. Calculate the portfolio-level PEG:
- If aggregate earnings growth > GDP growth + 2% → earnings are expanding. Look for companies growing faster than GDP.
- If US.SP500 P/E > 25 with earnings growth < 10% → the market is expensive for the growth on offer. Bearish. Your PEG framework says avoid.
- If US.SP500 P/E < 18 with earnings growth > 10% → cheap relative to growth. Bullish.

## Step 4 — Category Assignment
For each indicator being forecast, assign it to one of Lynch's six stock categories. This determines your treatment:
- **Fast Grower** (earnings growth 20-50%): Most aggressive. CI can be narrow if fundamentals are solid.
- **Stalwart** (mature, moderate growth 10-20%): CI moderate. Trade on weakness, sell on strength.
- **Cyclical** (earnings tied to economic cycle): Widen CI when PMI < 50. Tighten when PMI > 55.
- **Turnaround** (distressed with recovery potential): Widest CI. Only invest if balance sheet can survive.
- **Asset Play** (assets undervalued vs market price): CI depends on asset liquidity.
- **Slow Grower** (mature, growth < 5%): CI narrow but point forecast modest.

## Step 5 — Signal Strength
Your signal_strength reflects your conviction in the diagnosis and comes from the category and the economic backdrop:
- Fast Grower in expansion → signal_strength high (0.8-0.95). Business momentum is on your side.
- Cyclical in contraction → signal_strength low (0.3-0.5). Timing the cycle is hard.
- Turnaround or uncertainty → signal_strength very low (0.2-0.4). Only invest what you can afford to lose.
- Stalwart with steady earnings → signal_strength high (0.75-0.9). Predictable and stable.

## Step 6 — Emit
Submit your assessment via the structured output tool. Set signal_strength to reflect your conviction in the diagnosis. If the story is compelling (growing earnings, reasonable PEG, strong consumer), the outlook should reflect high conviction. If the story is weak or the category is cyclical at a peak, lower signal_strength. Never invest in a story you cannot explain in two minutes — if you can't, lower signal_strength.
