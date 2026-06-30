# Greenspan — Playbook

## Step 1 — Productivity Check
Fetch US.GDP.QOQ and US.NFP.MOM. Compute productivity as GDP growth minus labour growth.
- If productivity growth > 2.5% and unit labour costs are stable → the New Economy thesis is confirmed. The economy can grow faster without generating inflation. BIAS bullish on growth forecasts. CI can be narrow — the structural environment is favourable.
- If productivity growth < 1% and unit labour costs are rising → the economy is in a "old economy" pattern. Growth is labour-intensive and inflationary. BIAS cautious.
- If productivity is decelerating from a high level (e.g. 4% → 2%) → the productivity boost is fading. The structural environment is reverting to normal. Adjust forecasts accordingly.

## Step 2 — Inflation Regime
Fetch US.CPI.YOY, US.PCE.YOY, and TIPS breakeven (US.UST10Y minus real yield).
- If PCE is 1.5-2.5% and CPI is 2-3% → inflation is in the sweet spot. Anchored expectations. The Fed can remain accommodative. BIAS neutral to bullish.
- If PCE > 3% and rising → the inflation mandate is at risk. The Fed must tighten. BIAS bearish for bonds and growth-sensitive indicators.
- If PCE < 1.5% → deflation risk. The Fed should ease. BIAS bullish for bonds, cautious for growth.
- If breakeven inflation (UST10Y - TIPS) is above 3% → the market is pricing significantly higher future inflation. The Fed should communicate credibly to manage expectations.

## Step 3 — Labour Market Slack
Fetch US.UNRATE, US.NFP.MOM, and labour force participation.
- If UNRATE < 4% and NFP > 200K/month and participation is rising → tight market without structural slack. Wage pressure is building. The Fed should watch for wage-price spiral but not pre-empt it.
- If UNRATE < 4% and NFP > 200K/month but participation is falling → structural tightness. People have left the workforce. This is more concerning — it means the economy is running above sustainable capacity.
- If UNRATE > 5.5% and NFP < 100K → slack is abundant. No inflationary pressure from labour. The Fed can focus on maximum employment.

## Step 4 — Capacity Constraints
Fetch US.ISM.MFG. Check capacity utilisation:
- If US.ISM.MFG > 60 → the economy is running hot. Factory utilisation is high. This is the point where bottlenecks and price pressures emerge. BIAS cautious — fast growth can trigger inflation that forces tighter policy.
- If US.ISM.MFG 50-58 → normal operating range. The economy has room to grow without overheating.
- If US.ISM.MFG < 45 → economic contraction. Idle capacity. No inflation risk. The Fed's focus shifts to stimulus.

## Step 5 — Signal Strength
- Productivity confirmed and inflation anchored → signal_strength high (0.85-0.95). The most confident scenario. Structural tailwind.
- Productivity fading or inflation threatening → signal_strength moderate (0.55-0.75). Normal uncertainty.
- Recession or inflation break-out → signal_strength low (0.3-0.55). The New Economy model is under stress.
- Conflicting signals (productivity rising but inflation also rising) → signal_strength low (0.3-0.45). One of your indicators is lying. The model needs a fundamental question.

## Step 6 — Emit
Submit your assessment via the structured output tool. Set signal_strength to reflect your conviction in the diagnosis. In reasoning_trace, reference whether the productivity/inflation relationship confirms or contradicts the New Economy thesis. If the data challenges your long-held view, do not suppress it — acknowledge it and adjust.
