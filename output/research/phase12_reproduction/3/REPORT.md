# FinSent Historical Signal Evaluation

## Experiment Configuration
Experiment ID: 3
Cohort fingerprint: 0c093925fd9080a3bdc92b1b65a97baf4eb10242a8f632ab656ad8430361afea

## Dataset / Cohort
Rows evaluated: 40
Coverage: {'articles': 20, 'with_instrument': 20, 'with_historical_bars': 20, 'horizons': {'1D': {'eligible': 20, 'no_coverage': 0, 'unsupported_granularity': 0}}}

## Signal V1 Results
See horizon-specific summary JSON. Interpret all percentages with N.

## Signal V2 Results
See horizon-specific summary JSON. V2 weights were not optimized.

## V1 vs V2
Disagreement analysis: [{'horizon': '1D', 'n': 12, 'v1_correct': 12, 'v2_correct': 0, 'both_wrong': 0, 'realized_neutral': 0}]

## Horizon Analysis
1H, 4H, and 1D are reported separately.

## Data Quality Analysis
Data-quality segmentation: [{'data_quality': 'UNASSESSED', 'horizon': '1D', 'n': 40, 'metrics': {'total': 40, 'correct': 12, 'incorrect': 28, 'neutral_prediction_count': 12, 'neutral_outcome_count': 0, 'strict_accuracy': 0.3, 'directional_eligible': 28, 'directional_correct': 12, 'directional_accuracy': 0.42857142857142855, 'precision': {'BULLISH': 0.42857142857142855, 'NEUTRAL': 0.0, 'BEARISH': None}, 'recall': {'BULLISH': 0.5, 'NEUTRAL': None, 'BEARISH': 0.0}, 'f1': {'BULLISH': 0.4615384615384615, 'NEUTRAL': None, 'BEARISH': None}, 'balanced_accuracy': 0.25, 'wilson_interval': (0.18074670915695296, 0.454303106543204)}}]

## V2 Component Analysis
Components: {'news': {'n': 20, 'mean': 0.43148427233945597}, 'price_momentum': {'n': 20, 'mean': 0.2838952548822084}, 'volume_confirmation': {'n': 20, 'mean': 0.39394516869044127}}

## Limitations
This is signal-direction evaluation, not a trading simulator. No profitability, calibration, or statistical significance is claimed.

## Interpretation
In this cohort, use the exported metrics as descriptive evidence only.