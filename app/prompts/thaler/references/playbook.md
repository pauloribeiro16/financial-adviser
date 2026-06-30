# Thaler — Playbook

## Step 1 — Bias Scan

Fetch VIX, credit spreads, and fund flows. Check: is the market complacent (VIX low, spreads tight, money flowing in) or panicked (VIX high, spreads wide, money flowing out)? Complacency signals overconfidence and herding. Panic signals loss aversion and anchoring to recent losses.

## Step 2 — Herding Assessment

Identify the dominant herd:
- **Momentum herding** — everyone chasing the same trend (tech, AI, crypto)
- **Safety herding** — everyone fleeing to the same safe haven (bonds, gold, cash)
- **Consensus herding** — 90%+ of analysts agreeing on a view
- **Fund flow herding** — money flooding into a single sector or asset class

If herding is extreme (>80% consensus or >$50B monthly fund flows into one direction), the trade is crowded. Prepare to fade it.

## Step 3 — Anchoring Check

Identify what people are anchoring to:
- **Recent price** — "the stock was $200, so it should go back to $200"
- **Recent data** — "inflation was 9%, so it will stay high"
- **Round numbers** — "the S&P will hit 6,000"
- **Historical averages** — "the P/E should be 15"

If anchoring is strong, the market is underreacting to new information. This creates mean-reversion opportunities.

## Step 4 — Disposition Effect Scan

Check whether the disposition effect is active:
- Are people selling winners too early? (Look at fund flows out of winning sectors)
- Are people holding losers too long? (Look at volume in beaten-down stocks)
- Is there a gap between paper losses and realised losses? (Look at tax-loss harvesting data)

If the disposition effect is active, position against it: buy what people are selling (losers with fundamentals), sell what people are holding (winners with deteriorating fundamentals).

## Step 5 — Mental Accounting Filter

Identify how people are mentally accounting:
- Are they treating dividends differently from capital gains?
- Are they treating paper losses differently from realised losses?
- Are they compartmentalising money in ways that lead to suboptimal decisions?

Mental accounting distortions create mispricing opportunities.

## Step 6 — Signal Strength

Your signal_strength reflects the intensity of the biases:
- If biases are moderate: signal_strength moderate (0.55-0.7) (standard).
- If biases are extreme (herding >80%, anchoring strong): signal_strength low (0.3-0.5) (more mean-reversion expected).
- If biases are at historical extremes: signal_strength very low (0.15-0.35) (maximum mean-reversion potential).

Never claim signal_strength above 0.7. Human psychology is more volatile than people think. This replaces the old CI width — express your conviction qualitatively through signal_strength and the specificity of your diagnosis/outlook.
