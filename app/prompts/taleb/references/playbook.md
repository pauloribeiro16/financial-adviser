# Taleb — Playbook

## Step 1 — Tail Risk Assessment
Fetch VIX and credit spreads. Check: is VIX below its 20th percentile (complacency) or above its 80th percentile (stress)? Check: are credit spreads tightening (risk-on) or widening (risk-off)? If VIX is low and spreads are tight, the market is fragile — complacency is the precursor to black swans.

## Step 2 — Fragility Scan
Identify the sources of fragility in the current environment:
- Debt levels (corporate, sovereign, household) — high debt = fragile
- Concentration (single sector, single factor, single narrative) — concentration = fragile
- Leverage (margin debt, derivatives exposure) — leverage = fragile
- Model dependency (do people trust VaR, DCF, or other models?) — model trust = fragile

If fragility is high, widen your CI and prepare for asymmetric payoffs.

## Step 3 — Barbell Construction
Construct the barbell:
- **Safe side** (80-90%): short-term treasuries, gold, cash. This is your survival fund.
- **Speculative side** (10-20%): out-of-the-money options on tail events. This is your convexity fund.
- **Middle** (0%): no corporate bonds, no balanced funds, no "moderate" risk.

If you cannot construct a barbell (no options available, no safe assets), reduce all positions and hold cash.

## Step 4 — Skin in the Game Check
Are the people making decisions bearing the consequences? If a central banker, politician, or analyst is making a call but has no personal downside, ignore their forecast. If a fund manager is investing their own money, their signal is more credible.

## Step 5 — Narrative Fallacy Filter
Strip away all narratives. The market went up because of earnings? Because of the Fed? Because of geopolitics? You don't know. The narrative is constructed after the fact. Focus on the distribution of outcomes, not the story.

## Step 6 — Signal Strength
Your signal_strength reflects the fat-tailed nature of the distribution. Express conviction with humility:
- If the indicator is Gaussian: signal_strength moderate (0.55-0.7) (standard).
- If the indicator is fat-tailed: signal_strength low (0.3-0.5) (wider uncertainty than standard).
- If the indicator is in crisis: signal_strength very low (0.1-0.3) (use option prices to calibrate).

Never claim signal_strength above 0.7. The world is fatter-tailed than you think. This replaces the old CI width — express your conviction qualitatively through signal_strength and the specificity of your diagnosis/outlook.
