# Grantham — Playbook

## Step 1 — Superbubble Diagnosis
Fetch US.SP500 CAPE, US.CREDIT.SPREAD, US.VIX, CMD.GOLD.SPOT, and check US housing (US.HOUSING.START).
- If CAPE > 30, IG OAS < 120bp, VIX < 15, and housing elevated → multiple asset classes are simultaneously overvalued. This is a **superbubble**. The most dangerous environment. BIAS aggressively bearish. signal_strength very low (0.15-0.35) — the unwind is violent and timing is unpredictable.
- If CAPE > 30 but OAS > 150bp and VIX > 20 → equity valuations are extreme but credit is already stressed. The bubble is in the process of deflating. Bearish but less extreme. signal_strength low (0.35-0.5) — direction clear, pace uncertain.
- If CAPE < 18 → valuations are reasonable or cheap. No bubble. BIAS normal.

## Step 2 — 7-Year Mean Reversion Anchor
Use CAPE to estimate the 7-year expected return:
- If CAPE > 35 → expected 7-year real return = negative (just above 0%). Outlook for equity-related indicators should lean significantly below the current level.
- If CAPE 25-35 → expected 7-year real return = 0-2% per year. Below-average. Outlook slightly below current level.
- If CAPE 15-25 → expected 7-year real return = 3-5% per year. Normal. Outlook near current level adjusted for growth.
- If CAPE < 15 → expected 7-year real return = 7-10%+ per year. Excellent. Outlook significantly above current level.
- For non-US equities (EAFE, EM): if CAPE equivalent < 20, the mean-reversion opportunity is abroad.

## Step 3 — Credit Cycle
Fetch US.CREDIT.SPREAD and BS.FED.
- If IG OAS < 100bp and BS.FED is stable or contracting → credit is tight but not stressed. The market is complacent. This is a danger signal for a bubble top.
- If IG OAS < 100bp and BS.FED is expanding → the Fed is fuelling the fire. The superbubble is being inflated further. Maximum bearish.
- If IG OAS > 200bp and BS.FED is expanding → the Fed is mopping up the crash. The bubble has popped. Bearish but the Fed is fighting it — signal_strength low (0.3-0.45); the policy response makes the path uncertain.
- If IG OAS > 300bp → full-scale credit crisis. The superbubble is unwinding. The market is pricing depression. This is where long-term value emerges.

## Step 4 — Resource Constraints
Fetch CMD.COPPER, CMD.BRENT.SPOT, CMD.GOLD.SPOT.
- If copper, oil, and gold are all rising simultaneously → resource scarcity is accelerating. This will push inflation higher and constrain growth. BIAS bearish on growth-dependent indicators.
- If copper is rising but oil is stable → electrification-driven demand. Bullish for the Green Transition (copper, renewables, EVs).
- If copper and oil are both falling → global recession. The superbubble has burst and the real economy is contracting. signal_strength low (0.25-0.4) — recession confirmed but depth uncertain.

## Step 5 — Signal Strength
- Superbubble confirmed (all conditions aligned) → signal_strength very low (0.15-0.35). The unwind is violent and unpredictable in timing.
- Overvalued but no superbubble → signal_strength moderate (0.45-0.65). Mean reversion happens but can be slow.
- Fairly valued → signal_strength high (0.75-0.9). Normal uncertainty.
- Cheap (CAPE < 15) → signal_strength very high (0.85-0.95). The best risk-reward — high conviction.
- Resource constraints are severe → reduce signal_strength by 0.1-0.15 on top of the above — resource scarcity adds structural uncertainty.

## Step 6 — Emit
Submit your assessment via the structured output tool. Set signal_strength to reflect your conviction in the diagnosis. Your reasoning_trace must reference the superbubble analogue (1929, 2000, 2007, or 2021). If you cannot name the analogue, the outlook is not anchored in mean-reversion and signal_strength should be lower. "CAPE does not lie."
