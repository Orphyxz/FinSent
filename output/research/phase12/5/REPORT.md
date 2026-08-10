# FinSent Historical Signal Evaluation

## Experiment Configuration
Experiment ID: 5
Cohort fingerprint: b6299de35bd8bbd6ab88b2d071329e1dba227f356f07597c9081489fbe217db2

## Dataset / Cohort
Rows evaluated: 366
Coverage: {'articles': 183, 'with_instrument': 183, 'with_historical_bars': 183, 'horizons': {'1D': {'eligible': 159, 'no_coverage': 0, 'unsupported_granularity': 0}}}

## Signal V1 Results
See horizon-specific summary JSON. Interpret all percentages with N.

## Signal V2 Results
See horizon-specific summary JSON. V2 weights were not optimized.

## V1 vs V2
Disagreement analysis: [{'horizon': '1D', 'n': 30, 'v1_correct': 6, 'v2_correct': 9, 'both_wrong': 15, 'realized_neutral': 9}]

## Horizon Analysis
1H, 4H, and 1D are reported separately.

## Data Quality Analysis
Data-quality segmentation: [{'data_quality': 'UNASSESSED', 'horizon': '1D', 'n': 318, 'metrics': {'total': 318, 'correct': 73, 'incorrect': 245, 'neutral_prediction_count': 132, 'neutral_outcome_count': 66, 'strict_accuracy': 0.22955974842767296, 'directional_eligible': 153, 'directional_correct': 40, 'directional_accuracy': 0.26143790849673204, 'precision': {'BULLISH': 0.26490066225165565, 'NEUTRAL': 0.25, 'BEARISH': 0.0}, 'recall': {'BULLISH': 0.2777777777777778, 'NEUTRAL': 0.5, 'BEARISH': 0.0}, 'f1': {'BULLISH': 0.2711864406779661, 'NEUTRAL': 0.3333333333333333, 'BEARISH': None}, 'balanced_accuracy': 0.25925925925925924, 'wilson_interval': (0.18672805968935435, 0.27884755266156613)}}]

## V2 Component Analysis
Components: {'news': {'n': 183, 'mean': 0.2908622292952914}, 'price_momentum': {'n': 183, 'mean': 0.3515902587384337}, 'volume_confirmation': {'n': 183, 'mean': 0.0839585299259459}}

## Limitations
This is signal-direction evaluation, not a trading simulator. No profitability, calibration, or statistical significance is claimed.

## Interpretation
In this cohort, use the exported metrics as descriptive evidence only.