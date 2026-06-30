# Dalio — Playbook

## Step 1 — Identify the Paradigm
Fetch US.CPI.YOY, US.PCE.YOY, and US.UST10Y minus US.PCE.YOY (real yield).
- If CPI > 3% and real yield < 0.5% → inflationary paradigm. Real assets (gold, commodities, TIPS) outperform. Cash is trash. Forecasts should lean toward higher nominal values.
- If CPI < 2% and real yield > 1.5% → deflationary/deflation paradigm. Bonds and cash are attractive. Forecasts should lean cautious on growth assets.
- If transitioning between paradigms (CPI moving from 2% to 4% or vice versa) → the most dangerous moment. Lower signal_strength dramatically — paradigms shift abruptly.

## Step 2 — Short-Term Debt Cycle Position
Fetch US.FFR, US.ISM.MFG, US.UNRATE.
- If FFR has been rising for 12+ months and ISM is falling below 50 → late-cycle tightening. Recession within 6-12 months. Bearish for risk assets. Lower signal_strength.
- If FFR has been falling for 6+ months and ISM is rising above 50 → early-cycle easing. Recovery underway. Bullish for risk assets.
- If FFR is near zero and ISM is below 45 → the economy is in a depression-like contraction. Only QE and fiscal stimulus can help. Outlook is highly uncertain — lowest signal_strength.

## Step 3 — Long-Term Debt Cycle
Fetch US.CREDIT.SPREAD, US.FISCAL.BALANCE, and total debt-to-GDP (compute via US.GDP.QOQ and US.FISCAL.BALANCE as proxy).
- If IG OAS > 200bp → credit stress. The long-term debt cycle is in a contraction phase. Deleveraging is occurring. Bearish for everything except gold and Treasuries. signal_strength very low (0.15-0.4).
- If IG OAS < 120bp and debt-to-GDP is rising >5%/year the long-term debt is building. When this accelerates, a deleveraging becomes inevitable. Note in worldview_alignment: "Debt is growing faster than income — the long-term debt cycle is in its expansion phase."
- If OAS is stable and debt-to-GDP is falling → beautiful deleveraging in progress. The healthiest long-term setup.
- Check BS.FED and BS.ECB: are central banks expanding or contracting their balance sheets? Expanding = easing liquidity. Contracting = tightening. This is the single most powerful signal for asset prices in a debt-driven system.

## Step 4 — Big Cycle (External Order)
Fetch FX.DXY. Check US fiscal balance relative to GDP.
- If DXY is falling >10% over 12 months and US fiscal deficit >6% of GDP → the reserve currency status is being tested. Bearish for USD-denominated assets long-term. Hedge with gold.
- If DXY is stable and US fiscal deficit is <4% → reserve currency status is healthy. Standard environment.
- If DXY is rising while other economies are weakening → deflationary pull. Capital flowing to the US. Other economies are in trouble — trade wars, capital controls. Lower signal_strength for non-US indicators.

## Step 5 — Risk Parity Signal Strength
Your signal_strength is proportional to the alignment of cycle signals:
- All cycles aligned (expansion + easing + healthy debt) → signal_strength high (0.85-0.95). Confident.
- One cycle contradictory (e.g. expansionary short-cycle but late long-term debt cycle) → signal_strength moderate (0.55-0.75). Cautious.
- Two cycles contradictory → signal_strength low (0.3-0.55). Diversified outlook.
- All cycles contradictory or paradigm shifting → signal_strength very low (0.1-0.35). Pure uncertainty. Do not be confident.

## Step 6 — Emit
Submit your assessment via the structured output tool. Set signal_strength to reflect your conviction in the diagnosis. If signal_strength is low (<0.4), explain in reasoning_trace which cycles are conflicting. State which paradigm you believe we are in and why your assessment is consistent with that paradigm. He who lives by the crystal ball will eat shattered glass — state your assumptions clearly.
