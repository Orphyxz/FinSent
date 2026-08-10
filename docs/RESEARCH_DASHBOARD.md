# Research Dashboard

The Research page presents the locked Phase 16 final-holdout results inside the Dash UI.

## Source Artifacts

The page reads:

- `output/research/phase16/FINAL_EVALUATION_SUMMARY.json`
- `output/research/phase16/FINAL_RESULTS_MANIFEST.json`

The loader verifies:

- Expected final holdout fingerprint: `8b2baffa76672e164ee5c29be3858f81d7c985615a0b3a0fb45e452fd2a3b93e`
- Manifest status: `FINAL_HOLDOUT_V3_EVALUATED_LOCKED`
- Summary JSON SHA-256 against the manifest hash

If artifacts are missing, invalid, or mismatched, the page shows an unavailable or warning state instead of inventing values.

## Displayed Results

- Cohort metadata: final N, represented eligible symbols, horizon, news source, sentiment model, and price source.
- Signal V1 and Signal V2.0 metrics: strict accuracy, directional accuracy, balanced accuracy, and macro F1.
- Baseline context: majority class, majority balanced accuracy, always neutral, and news direction.
- Confusion matrices for V1 and V2.0.
- Class-distribution chart across realized direction, FinBERT, V1, and V2.0.
- Paired correctness chart and McNemar non-run note.
- Per-symbol strict-accuracy chart for AMZN, NVDA, and TSLA.
- V2.1 unpromoted research-candidate metrics.
- Descriptive V2 component and confidence-calibration panels.

## Interpretation Boundary

The page supports only the conclusions already supported by Phase 16:

- Results describe the locked FNSPID/Yahoo daily 1D cohort.
- Signal V1 outperformed Signal V2.0 on strict accuracy, balanced accuracy, and macro F1 in this cohort.
- Signal V2.1 remains an unpromoted research candidate.
- Identity confidence calibration remains selected because no calibration was justified.

The page does not support profitability, market-beating, trading, production generalization, or future performance claims.

## Read-Only Contract

The Research page does not write database experiment rows, sentiment runs, signal runs, event-study results, or artifact files. Phase 17 tests include a database count guard around `research.layout()` to preserve that boundary.

