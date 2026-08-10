# Evaluation Harness

Phase 8 adds a small operational harness for future event-study evaluation. It does not run broad historical experiments or claim accuracy.

## Components

- `EventStudyServiceV2`: builds inputs, evaluates horizons, and optionally persists results.
- `EventStudyBatchRunnerV2`: evaluates a small list of supplied events or stored articles.
- `python -m finsent.scripts.run_event_study_v2`: safe CLI over stored local DB data.

## CLI

```powershell
python -m finsent.scripts.run_event_study_v2 --symbol AAPL --horizon 1h --limit 5
```

Options:

- `--symbol`
- `--horizon 1h|4h|1d`, repeatable
- `--persist`
- `--experiment-id`
- `--limit`, default `5`

The CLI never processes the full database by default.

## Experiment Linkage

V2 results can store optional:

- `experiment_id`
- `article_id`
- `sentiment_run_id`
- `signal_run_id`

This allows future research to connect sentiment/model runs, Signal V2 outputs, and realized event-study returns.

## Leakage Boundary

Signal/event construction at `T0` must not use future bars or future articles. Event Study V2 consumes future prices only as outcome measurement after the event has already been defined.

The harness is plumbing for later research. It does not optimize Signal V2 weights, thresholds, or confidence.

## Model Comparison

Phase 9 adds `GeminiFinBertExperimentRunner` and `python -m finsent.scripts.run_model_comparison`. The model-comparison runner uses Event Study V2 as the realized-outcome layer for paired Gemini/FinBERT observations.

Dry-run mode reports selected articles, credential/dependency readiness, expected model execution counts, and Event Study V2 coverage without model calls or writes.

## Historical Signal Evaluation

Phase 10 adds `HistoricalSignalEvaluator` and `python -m finsent.scripts.run_signal_evaluation`.

The runner builds a deterministic article cohort, evaluates frozen Signal V1 and explicit Signal V2 at each article timestamp, then measures realized returns with Event Study V2. Dry-run mode builds the cohort and reports expected V1/V2 run counts without writing rows.

This remains a descriptive research harness. It does not simulate trades, optimize thresholds, or alter any signal/event-study formula.
