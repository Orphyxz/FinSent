# Final Evaluation Protocol

Phase 16 may evaluate only frozen systems: Signal V1 and Signal V2.0 as primary systems, with V2.1-research only as an explicitly unpromoted research candidate.

Metrics: strict accuracy, directional accuracy, balanced accuracy, macro F1, class precision/recall, confusion matrix, coverage, Wilson interval, and paired V1/V2 correctness. McNemar may be used if discordant N is sufficient.

Baselines: majority-class, always-neutral, and news-direction baseline.

Interpretation: V2 is not supported merely by a higher point estimate; balanced accuracy, macro F1, paired results, uncertainty, baselines, and sample size must all be considered.

## Post-Evaluation Note

Phase 16 executed this preregistered protocol once on `phase15_final_holdout_v3`. This note records execution only and does not revise methodology.
