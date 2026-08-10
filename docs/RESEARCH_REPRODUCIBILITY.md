# Research Reproducibility

Phase 9 makes Gemini-vs-FinBERT comparisons reproducible through explicit configuration, deterministic selection, immutable model/event rows, and stable exports.

Phase 10 extends the same principle to historical Signal V1/V2 evaluation. Cohorts are fingerprinted, signal inputs are bounded at article time `T0`, Event Study V2 outcomes are attached after signal generation, and CSV/JSON/Markdown exports are generated from immutable rows.

Phase 11 adds source manifests for external historical-news and price subsets, plus a locked preliminary real-data cohort.

Phase 12 adds explicit preregistration, stratified FNSPID acquisition, temporal development/holdout split, paired V1/V2 correctness tables, simple baselines, Wilson intervals, and a read-only Signal V2 parameter registry for future tuning.

Phase 13 renames the inspected Phase 12 holdout to OBSERVED_VALIDATION, freezes Phase 12 artifact references, locks a new future-period `FINAL_HOLDOUT_LOCKED` cohort, and runs Signal V2.1 research tuning only on the Phase 12 DEVELOPMENT rows.

## Configuration

`ModelComparisonConfig` records:

- experiment name/type
- dataset id
- symbols and markets
- date range
- providers
- maximum article count
- random seed
- requested horizons
- reuse/force-rerun flags
- Gemini/FinBERT model identifiers where available
- sentiment-normalization version
- Event Study V2 engine version

The configuration is persisted through `ExperimentRun.configuration_json` when execution is persisted.

## Deterministic Selection

Stored articles are filtered and deduplicated before sampling. If the eligible set is larger than the cap, seeded sampling is used.

## Immutable Runs

Model outputs are stored in `sentiment_analysis_runs`. Event outcomes are stored in `event_study_results`. Aggregated metrics are recomputable from these immutable rows, so Phase 9 does not add an aggregate metrics table.

## Reuse Fingerprints

Run reuse requires an exact compatible fingerprint. The fingerprint includes article identity/text hash, model family/name/version, analysis method, normalization version, and prompt/config identity.

## Export

Exports are written under:

```text
output/research/<experiment_id>/
```

Files:

- `paired_results.csv`
- `summary.json`

Exports omit secrets and raw article body text by default.

Phase 10 signal-evaluation exports add:

- `signal_evaluation_rows.csv`
- `signal_evaluation_summary.json`
- `REPORT.md`

## No Lookahead

Model analysis receives article text and article context only. Realized future returns from Event Study V2 are added later as evaluation outputs and must not feed sentiment prompts or normalization.

Historical Signal V1/V2 evaluation follows the same boundary: articles and signal price bars must be timestamped at or before `T0`; future bars are consumed only by Event Study V2 as realized outcomes.

The Phase 11 preliminary evaluation uses only the FinBERT-analyzed article window for the first real signal run; unanalyzed imported rows remain available but are not mixed into that preliminary metric set.

Phase 12 uses the same no-lookahead boundary on the locked cohort. Yahoo chart daily bars are used as signal history only when timestamped at or before `T0`; future bars are consumed only by Event Study V2 outcome measurement.

Phase 13 adds a guard that refuses normal historical signal evaluation for `phase13_final_holdout_v1`. The final holdout may have technical coverage checked, but Phase 13 must not calculate signal accuracy, balanced accuracy, confusion matrices, realized-direction summaries, or component/outcome relationships for it.

## Live Execution Policy

If Gemini credentials or FinBERT dependencies are absent, dry-run and reuse paths still work. The framework must not fabricate Gemini outputs or silently relabel heuristic output as Gemini.

## Phase 14

Phase 14 stores confidence calibration artifacts and holdout adequacy/retirement metadata under `output/research/phase14/`. Final-holdout performance remains unevaluated.

## Phase 15

Phase 15 preregisters the final evaluation protocol before final performance exists and locks only technical holdout metadata.

## Phase 16 Final Evaluation

Final result manifest: `output/research/phase16/FINAL_RESULTS_MANIFEST.json`. Results hash set: `{'row_export': '7d0636691dc1c81be8387c856e36a8e84147b135922405ec1f99cb24c5f913ee', 'summary_json': '167c9748dff2afb8a0f8edf76f6766d10aae9b381299499710fe6d9cabe139fe', 'final_report': '766d3a6279576ef557587b4387be997bb7ec0c2bcf82e8e02a533870b92ca43e', 'pre_execution_manifest': '359557f1f674a10123be2f0f738b7b3c930ebf58c3b15c4fd59ee32f29a7ceb1', 'execution_config': '3ed363824945be911a10b873fd417560a7e3b8fa5869645f52f89db219292a53', 'holdout_status': 'a0b4fb6dedf138c36e672b5082774cea609f8e6326a5727eec363d61c16e803b'}`.
