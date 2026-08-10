# Signal V2.1 Research Candidate

The candidate is frozen for research only and is not the dashboard default.

```json
{
  "candidate": {
    "candidate_id": "v2_1_grid_042",
    "directional_threshold": 0.15,
    "momentum_weight": 0.45,
    "news_weight": 0.55,
    "volume_weight": 0.0
  },
  "confidence_formula": "unchanged from V2.0: 0.35*abs(score)+0.30*reliability+0.20*agreement+0.15*availability",
  "created_at": "2026-08-10T00:41:42.644823",
  "engine_name": "finsent_composite",
  "engine_version": "2.1-research",
  "momentum_return_scale": 0.05,
  "news_decay": {
    "max_news_age_hours": 72.0,
    "min_news_recency_weight": 0.2
  },
  "parent_version": "2.0",
  "status": "FROZEN_RESEARCH_CANDIDATE_NOT_JUSTIFIED",
  "strong_threshold": 0.55,
  "tuning_dataset_fingerprint": "62a7844695106cd34bb4bd8f2583483e3af2394876b9728502a4dc30cf4e039b",
  "tuning_method": "Phase 12 DEVELOPMENT rows only; 3-fold chronological expanding-window validation; median balanced accuracy objective."
}
```

## Phase 16 Final Note

V2.1 remained an unpromoted secondary research candidate during final evaluation.
