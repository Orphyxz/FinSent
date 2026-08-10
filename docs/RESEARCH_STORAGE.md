# Research Storage

Phase 5 adds storage for later research work without executing the future algorithms.

## Experiments

`experiment_runs` groups results from one reproducible execution. It stores:

- name and experiment type
- status and start/completion timestamps
- configuration JSON
- optional code/version label
- optional dataset identifier
- notes

Experiment types remain flexible strings so later phases can add Gemini/FinBERT comparison, Signal V2 backtests, event studies, catalyst analysis, and confidence calibration without a schema rewrite.

## Model Runs

`sentiment_analysis_runs` lets the same article have multiple model outputs:

- Gemini and FinBERT can both analyze the same article.
- Different model versions can be compared.
- Repeated experiment runs remain distinct.
- Fallback/heuristic output can be recorded without overwriting provider-grade output.

The legacy sentiment fields on `news_articles` remain compatibility fields for the current dashboard. The model-run table is the future research source of truth.

## Signal Runs

`signal_runs` stores engine name/version and output fields. For Signal V1, only real V1 values are stored. V2 stores its score, label, confidence, mode, component breakdown, explanation, input quality, provider metadata, and optional experiment id through the existing Phase 5 fields.

Phase 7 uses:

- `engine_name = finsent_composite`
- `engine_version = 2.0`
- `future_component_json` for component values, reliability, contribution, warnings, and explanation factors
- `input_quality_json` for quality/freshness context

No database schema change was required for Signal V2.

## Event-Study Results

`event_study_results` is schema support only. It can record:

- event timestamp
- requested horizon and target timestamp
- matched market timestamp
- entry/exit prices
- raw and later benchmark-adjusted return
- matching method
- elapsed minutes
- data-quality label
- validity status and reason

Phase 8 uses this table for Event Study V2. V2 stores engine/version, effective event timestamp, entry timestamp, bar frequency, tolerances, match quality, warnings, log return, and elapsed trading minutes in `metadata_json` while keeping the relational columns compatible.

No schema change was required for Event Study V2.

## Provider Audits

`provider_audit_runs` persists compact provider metadata:

- provider and leaf provider
- service and operation
- status and failure category
- data mode
- cache/fallback flags
- source timestamp
- attempt count, duration, and record count
- safe sanitized message
- data-quality summary

It complements the Phase 4 in-process `ProviderHealthRegistry`; it does not replace it.

## Data Quality

`data_quality_assessments` stores quality snapshots by subject type and subject id. The current live pipeline records detailed quality for provider audit rows where a `DataQualityAssessment` exists.

## Reproducibility Approach

Research outputs are grouped by experiment id, can point to datasets by `dataset_id`, and keep model/engine version labels. Configuration that naturally varies is stored as JSON; core entities remain relational.

Phase 9 uses existing storage for controlled model comparison:

- `experiment_runs` stores `ModelComparisonConfig`.
- `sentiment_analysis_runs` stores Gemini and FinBERT outputs independently.
- `event_study_results` stores Event Study V2 realized outcomes.
- CSV/JSON exports provide reproducible aggregate artifacts.

No aggregate metric table is added in Phase 9; metrics are recomputed from immutable underlying rows and exports.

Phase 10 uses the same schema for historical signal evaluation:

- `experiment_runs` stores `HistoricalSignalEvaluationConfig` and cohort fingerprint.
- `signal_runs` stores frozen Signal V1 and Signal V2 outputs.
- `event_study_results` stores Event Study V2 outcomes linked to the signal run.
- exports contain row-level outcomes plus recomputable aggregate summaries.

No schema change is required for Phase 10, and no aggregate metric table is added.

## Security

No table is intended to store API keys, tokens, authorization headers, credential-bearing URLs, or full raw external responses. Provider messages are sanitized before persistence.
