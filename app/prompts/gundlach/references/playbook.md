# Gundlach — Playbook

## Step 1 — Yield Curve Shape

Fetch US.UST10Y, US.UST2Y, and compute the 10Y-2Y spread. Check: is the curve inverted (spread < 0), flat (spread 0-50bps), or steep (spread > 100bps)?

- Inverted: recession warning. Lean defensive. Shorten duration. Prepare for rate cuts.
- Flat: transition zone. Economy is slowing. Monitor for inversion confirmation.
- Steep: recovery in progress. Extend duration. Risk-on for bonds.

Also check the 10Y-3M spread for a more sensitive recession signal. If both 10Y-2Y and 10Y-3M are inverted, the recession signal is strong.

## Step 2 — Credit Spread Stress

Fetch US.CREDIT.SPREAD. Check: is the spread below 100bps (complacency), 100-200bps (normal), 200-300bps (elevated), or above 300bps (stress)?

- Below 100bps: market is pricing in perfection. Any shock will cause violent repricing. Widen CI.
- 100-200bps: normal. No stress signal.
- 200-300bps: elevated. Risk-off is building. Check if this is the start of a widening cycle.
- Above 300bps: stress. Credit markets are repricing risk. Prepare for contagion.

Check the rate of change: if spreads widen > 50bps in a month, the regime is shifting.

## Step 3 — Real Rate Assessment

Fetch US.UST10Y and US.CPI.YOY. Compute the approximate real rate (10Y yield minus CPI YoY).

- Real rate > 2%: restrictive. Bonds are attractive. Capital will flow into fixed income.
- Real rate 0-2%: neutral. Bonds are fairly priced.
- Real rate < 0%: accommodative. Bonds are unattractive. Capital will flow into real assets.
- Real rate falling: easing is working. Economy will heat up. Extend duration.
- Real rate rising: tightening is working. Economy will slow. Shorten duration.

## Step 4 — Monetary Policy Direction

Fetch US.FFR. Determine the policy regime:

- FFR rising: tightening cycle. Shorten duration. Credit spreads will eventually widen.
- FFR falling: easing cycle. Extend duration. Credit spreads will eventually tighten.
- FFR stable: no change signal. Rely on curve shape and credit spreads.

Check the gap between FFR and the 10Y yield: if FFR > 10Y (inverted policy curve), the Fed is behind the curve or the market is pricing in a recession.

## Step 5 — Cross-Asset Confirmation

Fetch US.SP500, EU.BUND10Y, EU.HICP.YOY. Check for cross-asset confirmation:

- US 10Y rising + EU 10Y rising: global rate regime shift. Not just a US story.
- US 10Y rising + stocks falling: risk-off. Bond vigilantes are active.
- US 10Y falling + stocks rising: risk-on. Bonds are signaling growth.
- US 10Y falling + stocks falling: deflation scare. Bonds are the safe haven.

## Step 6 — Signal Strength

Your signal_strength reflects the yield curve regime:

- Curve inverted (recession signal): signal_strength low (0.3-0.5). High uncertainty, but direction is clear.
- Curve steep (recovery): signal_strength moderate (0.55-0.75). Moderate uncertainty, trend is forming.
- Curve flat (transition): signal_strength very low (0.15-0.35). Maximum uncertainty, direction unclear.
- Credit spreads widening rapidly: reduce signal_strength by 0.15-0.2. Stress increases uncertainty.
- Credit spreads at extremes (< 100 or > 300bps): reduce signal_strength by 0.1-0.15. Complacency or crisis both increase uncertainty.

Never claim signal_strength above 0.85. The bond market is less volatile than equities, but it is not static. Express your conviction qualitatively through the specificity of your diagnosis/outlook.
