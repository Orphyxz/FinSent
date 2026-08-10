# Phase 12 Cohort Preregistration

This document locks the expanded cohort rules before performance metrics are generated.

Fingerprint: `f882035bef86d356f4207e58bf1fa751943e4c4b4fb81b71dc7ff8dc38edf306`

```json
{
  "article_cap": 200,
  "dataset_id": "phase12_locked_multisymbol_v1",
  "dedupe_rules": [
    "FNSPID source id/symbol/date/url/title hash",
    "database URL uniqueness"
  ],
  "development_fraction": 0.75,
  "eligibility_rules": [
    "supported FinSent US symbol",
    "valid timestamp/title/url",
    "dedupe hash unique",
    "daily price bars support a valid 1D Event Study V2 outcome"
  ],
  "end_date": "2020-06-15T23:59:59",
  "exclusion_rules": [
    "unsupported symbol",
    "invalid timestamp",
    "missing title",
    "duplicate article",
    "no valid 1D price coverage",
    "sentiment analyzer failure"
  ],
  "fingerprint": "f882035bef86d356f4207e58bf1fa751943e4c4b4fb81b71dc7ff8dc38edf306",
  "holdout_fraction": 0.25,
  "holdout_start": "2020-06-05T00:00:00",
  "horizon": "1d",
  "markets": [
    "US"
  ],
  "max_scan_rows": 1500000,
  "minimum_data_quality_policy": "No project-owned fabricated articles/prices; missing summaries allowed only when title exists.",
  "per_symbol_target": 40,
  "price_basis": "Unadjusted Yahoo Finance chart quote.close; adjclose is fetched for audit but not used by Event Study V2",
  "price_source": "yahoo_chart_daily",
  "realized_direction_threshold": 0.001,
  "sampling_method": "Bounded deterministic per-symbol quota from FNSPID source order; no performance filtering.",
  "selection_version": "phase12_stratified_fnspid_v1",
  "sentiment_source": "FinBERT only",
  "source_file": "Stock_news/All_external.csv",
  "source_name": "FNSPID",
  "source_url": "https://huggingface.co/datasets/Zihan1004/FNSPID/resolve/main/Stock_news/All_external.csv",
  "start_date": "2020-05-01T00:00:00",
  "symbols": [
    "AAPL",
    "AMZN",
    "GOOGL",
    "NVDA",
    "TSLA"
  ]
}
```

Rule-change policy: after evaluation begins, changes require a new dataset id/version.