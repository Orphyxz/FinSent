# Historical Signal Evaluation

Phase 10 adds an explicit framework for evaluating stored historical articles against Signal V1, Signal V2, and Event Study V2.

## CLI

Dry-run is the default safe behavior:

```powershell
python -m finsent.scripts.run_signal_evaluation --symbols AAPL --market US --limit 5
```

Execute with persistence only when the cohort is intentional:

```powershell
python -m finsent.scripts.run_signal_evaluation --symbols AAPL --market US --limit 5 --execute --export
```

Exports are written under `output/research/<experiment_id>/` when `--export` is used.

## Execution

For each selected article at `T0`, the evaluator:

1. Builds a deterministic research cohort.
2. Runs Signal V1 using only stored articles published at or before `T0` within the configured lookback.
3. Runs Signal V2 using the same past-known article set and price bars timestamped at or before `T0`.
4. Runs Event Study V2 after signal generation to measure realized `1H`, `4H`, and/or `1D` outcomes.
5. Reports metrics by engine and horizon.

## Metrics

The summary includes:

- strict accuracy
- directional accuracy
- precision, recall, and F1
- balanced accuracy
- V1/V2 disagreement analysis
- conditional returns by signal direction
- signal-mode segmentation
- data-quality segmentation
- V2 component summaries

Metrics are descriptive. Phase 10 does not claim profitability, calibration, or statistical significance.

## Persistence

Executed runs store:

- `experiment_runs` for the configuration and cohort fingerprint
- `signal_runs` for V1/V2 outputs
- `event_study_results` for realized outcomes linked to signal runs

No aggregate metrics table is added; metrics can be recomputed from immutable rows and exports.

## Boundaries

Signal V1 formulas, Signal V2 formulas, and Event Study V2 methodology are unchanged. Phase 10 is an evaluation layer, not a trading simulator or optimizer.

## Phase 12 Locked Baseline

Phase 12 adds a locked multi-symbol baseline report without changing Signal V1, Signal V2, or Event Study V2.

- rows export: `output/research/phase12/5/signal_evaluation_rows.csv`
- metrics export: `output/research/phase12/5/phase12_metrics.json`
- report: `output/research/phase12/5/PHASE12_BASELINE_REPORT.md`

Development and holdout are reported separately. Accuracy metrics exclude invalid Event Study V2 outcomes by horizon and always expose N.

## Phase 16 Final Holdout Boundary

Normal historical evaluation remains blocked for final holdout cohorts. Phase 16 used an explicit final-evaluation path with a sealed config hash.
