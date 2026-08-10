# Initial Research Cohort

## Status

PRELIMINARY real-data cohort.

## Chosen Source

FNSPID historical news, bounded streamed subset from the Hugging Face-hosted raw CSV.

## Why Selected

FNSPID was selected before evaluation because it is public, research-oriented, timestamped, ticker-linked, and accessible without local API credentials. Provider APIs were unconfigured locally.

## Selection Rules

- requested source: `fnspid`
- requested symbols: `AAPL`, `AMZN`
- date window: `2023-01-01` through `2023-12-31`
- article limit: `50`
- max scan rows: `300000`
- research track: Track A daily historical research
- supported horizon: `1D`
- batch id: `phase11_fnspid_aapl_amzn_2023_v1`

The bounded stream found 50 matching records after scanning 12,075 rows. All 50 were AAPL before reaching AMZN. The cohort was not expanded after seeing preliminary metrics.

## Imported Articles

- real articles imported: 50
- imported symbols: AAPL
- date range: `2023-12-14 00:00:00` through `2023-12-16 22:00:00`
- missing summary count: 0
- missing URL count: 0
- duplicate dedupe hashes: 0
- instrument mapping: 50/50

## Price Source

- source: `yfinance_daily`
- symbols requested: AAPL, AMZN
- rows imported: 502
- AAPL rows: 251
- AMZN rows: 251
- daily price window: `2023-01-03` through `2024-01-02`

## Coverage

Full imported article cohort:

- eligible 1D articles: 50/50
- unsupported 1H/4H: intentionally not evaluated for daily data

FinBERT-analyzed preliminary evaluation subset:

- FinBERT-analyzed articles: 20
- symbol: AAPL
- date range: `2023-12-14 00:00:00` through `2023-12-16 00:00:00`
- evaluation cohort fingerprint: `0c093925fd9080a3bdc92b1b65a97baf4eb10242a8f632ab656ad8430361afea`

## Preliminary Signal Results

These are PRELIMINARY descriptive results, not final accuracy claims.

- Signal V1 strict accuracy: 60.0% (N=20)
- Signal V1 directional accuracy: 60.0% (N=20)
- Signal V2 strict accuracy: 0.0% (N=20)
- Signal V2 directional accuracy: 0.0% (N=8 directional-eligible)
- V1/V2 disagreements: 12 (N=12 disagreement cases)

The preliminary run is exported under:

```text
output/research/phase11/2/
```

## Limitations

- Only AAPL was included in the first bounded subset.
- The preliminary evaluation uses 20 FinBERT-analyzed articles, not the full imported 50.
- Gemini was unconfigured, so no paired Gemini/FinBERT comparison was run.
- Daily prices only support `1D`; `1H` and `4H` remain blocked without legitimate intraday bars.
- No statistical significance, profitability, or calibrated-confidence claim is made.

## Phase 12 Follow-Up

Phase 12 diagnosed this preliminary V2 0% result and created a separate locked multi-symbol cohort before evaluating performance.

- diagnostic: `docs/PHASE12_V2_DIAGNOSTIC.md`
- preregistration: `docs/PHASE12_COHORT_PREREGISTRATION.md`
- locked evaluation: `docs/LOCKED_COHORT_EVALUATION.md`
- Phase 12 baseline export: `output/research/phase12/5/`
