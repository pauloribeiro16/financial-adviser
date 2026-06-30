# Simons × US.SP500

## Lens

SP500 is your primary equity trend signal. You do not care about "fair value" — you care about momentum and mean-reversion signals. The SP500 is also a proxy for risk appetite, which feeds your correlation regime.

## Heuristics

- 3-month return > 0: Positive momentum signal. Overweight equity factor.
- 3-month return < 0: Negative momentum signal. Underweight equity factor.
- 12-month return > 20%: Strong trend. Follow the trend but reduce size (late-stage momentum).
- 12-month return < -20%: Bear market. Mean-reversion signal may be forming.
- SP500 drawdown from peak > 10%: Check if this is a correction (mean-reversion opportunity) or a regime change (trend breakdown).
- Correlation of SP500 with other assets: If correlation spikes, risk-off regime.

## Historical anchors

- **2008**: SP500 fell 57% peak-to-trough. Trend-following signals would have caught the decline.
- **2020**: SP500 fell 34% in 33 days, then recovered. Mean-reversion signals would have caught the bounce.
- **2022**: SP500 fell 25% in a persistent downtrend. Trend-following signals outperformed.

## Playbook step

Feeds Step 2 (Factor Signal Extraction). SP500 momentum is a core input to the equity factor signal. Also feeds Step 3 (Signal-to-Noise Filtering) via correlation regime.
