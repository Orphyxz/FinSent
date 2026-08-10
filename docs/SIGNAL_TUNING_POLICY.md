# Signal Tuning Policy

Phase 12 is measurement-only. Signal V2 weights, thresholds, confidence coefficients, news decay, momentum normalization, and volume behavior are read-only.

Phase 13 performs the first controlled research-only tuning pass. The old Phase 12 HOLDOUT split is now OBSERVED_VALIDATION and is not pristine. A new `FINAL_HOLDOUT_LOCKED` cohort is reserved for a future explicit final-evaluation phase.

Future tuning rules:

- Use DEVELOPMENT split only for parameter experiments.
- Do not tune on OBSERVED_VALIDATION.
- Do not tune on FINAL_HOLDOUT_LOCKED.
- Version every parameter experiment.
- Do not repeatedly peek at validation data to select parameters.
- Evaluate FINAL_HOLDOUT_LOCKED only in a later explicit final-evaluation mode.
- Keep the Phase 12 locked cohort intact; create a new cohort version for genuine data-quality corrections.
- If Gemini becomes configured, run it on the same locked cohort rather than an easier replacement cohort.

Phase 13 allowed only a coarse grid over news weight, momentum weight, volume-confirmation weight, and symmetric directional threshold. The frozen research candidate is not justified for promotion because it did not materially improve median temporal-CV balanced accuracy over V2.0.

## Phase 14

Directional tuning remains closed. Confidence calibration may be fitted only on DEVELOPMENT data. FINAL_HOLDOUT_V2, if locked, is reserved for Phase 15 only.
