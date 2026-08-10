# Final Holdout Adequacy Policy

{
  "min_calendar_days": 14,
  "min_eligible_per_represented_symbol": 20,
  "min_symbols": 3,
  "min_total_eligible": 90,
  "status": "preregistered_before_replacement_outcome_inspection",
  "target_symbols": [
    "AAPL",
    "AMZN",
    "GOOGL",
    "NVDA",
    "TSLA"
  ]
}

## Phase 15 V3

V3 keeps the Phase 14 adequacy floor but uses robust per-symbol byte-range acquisition. It may lock four supported symbols when GOOGL is unavailable as a source symbol and GOOG is unsupported locally.
