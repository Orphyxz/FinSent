# Research Cohort Policy

Phase 10 cohorts are designed to be small, reproducible, and explicit.

Phase 11 locks the first preliminary real cohort after defining source, symbols, date window, limit, and horizon before evaluation.

## Eligibility

An article must have:

- non-empty title/headline
- parseable publication timestamp
- resolvable canonical instrument
- non-duplicate dedupe key within the cohort

Per-horizon coverage is then assessed with Event Study V2.

## Exclusion Reasons

Current reasons include:

- `MISSING_TITLE`
- `MISSING_TIMESTAMP`
- `MISSING_INSTRUMENT`
- `DUPLICATE_ARTICLE`
- `NO_PRICE_COVERAGE`
- `INVALID_EVENT_STUDY`
- `UNSUPPORTED_GRANULARITY`
- `SAMPLE_LIMIT`
- `BELOW_MINIMUM_QUALITY`

`BELOW_MINIMUM_QUALITY` is reserved for later explicit quality labels. Phase 10 does not infer quality labels from absent data.

## Splits

If `holdout_start` is configured:

- articles before it are `DEVELOPMENT`
- articles at or after it are `HOLDOUT`

The split is metadata only. It does not change Signal V1/V2 formulas.

## Sampling

If more samples are eligible than the configured limit, seeded random sampling selects the cohort and then sorts it by publication time/article id for deterministic processing.

## No Fabrication

No article, model output, price bar, realized return, or metric should be invented to fill a cohort. Missing data must remain visible as exclusion counts, invalid statuses, or zero evaluated rows.

Phase 11 did not expand the initial FNSPID subset after seeing preliminary metrics. The requested symbols were AAPL and AMZN, but the bounded 50-row stream filled with AAPL before reaching AMZN.

## Phase 12 Locked Cohort

Phase 12 uses preregistered stratified acquisition to prevent one symbol from monopolizing the cohort.

- dataset id: `phase12_locked_multisymbol_v1`
- symbols: AAPL, AMZN, GOOGL, NVDA, TSLA
- source window: `2020-05-01` through `2020-06-15 23:59:59`
- per-symbol target: 40 FNSPID source records
- holdout boundary: `2020-06-05 00:00:00`
- supported horizon: `1D`

The subset contained 200 source rows. URL-level database dedupe reduced the imported cohort to 183 articles. Invalid 1D Event Study V2 rows remain visible as `INVALID_EVENT_STUDY`; they are not silently discarded from the cohort record.
