# Phase 12 V2 Diagnostic

## Reproduction

Phase 11 was reproduced as experiment `3` with the same AAPL article window, stored FinBERT fields, Signal V1, Signal V2, and Event Study V2.

- V1 strict accuracy: 60.0% (N=20)
- V1 directional accuracy: 60.0% (N=20)
- V2 strict accuracy: 0.0% (N=20)
- V2 directional accuracy: 0.0% (N=8 directional-eligible)
- diagnostic export: `output/research/phase12_v2_diagnostic.csv`

## Evidence

- All 20 V2 rows ran in `NEWS_PLUS_MARKET`.
- News, momentum, and volume were available in all 20 rows.
- V2 predictions were 8 bullish and 12 neutral.
- Realized 1D outcomes were 12 bullish and 8 bearish.
- V2 score range was `0.143876` to `0.344434`.
- No mismatched V1/V2 article IDs, instruments, or timestamps were found in the reproduced export.

## FinBERT Mapping

FinBERT naturally lacks Gemini-specific fields such as catalyst, explicit relevance, impact rationale, and natural-language reason. The stored mapping does not collapse those missing fields to zero:

- missing relevance falls back to article/source relevance or relevant=true behavior
- missing impact strength falls back to `0.5`
- missing reason/catalyst does not remove a news item
- FinBERT articles contributed non-zero news weights when sentiment was directional

No implementation bug was confirmed in the FinBERT-to-V2 mapping.

## Classification

- `SMALL_SAMPLE_ARTIFACT`: strong evidence. The Phase 11 sample was 20 AAPL articles over a three-day window.
- `SIGNAL_MODE_LIMITATION`: partial evidence. V2 was entirely `NEWS_PLUS_MARKET`, but reliability inputs were unassessed and quote/liquidity was unavailable.
- `DATA_COVERAGE_LIMITATION`: partial evidence. Daily bars support only 1D and cannot test intraday behavior.
- `FINBERT_FIELD_LIMITATION`: partial evidence. FNSPID/FinBERT inputs are less expressive than Gemini-style catalyst/impact analysis.
- `GENUINE_OBSERVED_UNDERPERFORMANCE`: limited evidence on the Phase 11 cohort only.
- `IMPLEMENTATION_BUG`: not supported by the diagnostic.

## Conclusion

The 0% Phase 11 V2 result is best treated as a tiny-cohort observed failure plus input/mode limitations, not as proof of a formula bug. Signal V2 weights, thresholds, confidence, momentum, news decay, volume behavior, Event Study V2, and realized-return thresholds were not changed.
