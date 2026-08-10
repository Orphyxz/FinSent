# Final Holdout Preparation

PERFORMANCE NOT EVALUATED.

## Retired Holdout
{
  "adequate": false,
  "performance_evaluated": false,
  "previous_article_ids": [
    256,
    257,
    258,
    259,
    260,
    261,
    262,
    263,
    234,
    235,
    236,
    237,
    238,
    239,
    240,
    241,
    242,
    243,
    244,
    245,
    246,
    247,
    248,
    249,
    250,
    251,
    252,
    253,
    254,
    255
  ],
  "previous_coverage_summary": {
    "articles": 30,
    "horizons": {
      "1D": {
        "eligible": 30,
        "no_coverage": 0,
        "unsupported_granularity": 0
      }
    },
    "with_historical_bars": 30,
    "with_instrument": 30
  },
  "previous_dataset_id": "phase13_final_holdout_v1",
  "previous_date_end": "2023-12-13T00:00:00",
  "previous_date_start": "2023-12-12T00:00:00",
  "previous_fingerprint": "a6db3f66a5a648a755dca53325577e499f1fe607ab4b70d1e6c896133395b9c4",
  "previous_instruments": [
    "US:AAPL"
  ],
  "retired_at": "2026-08-10T19:12:37.257900",
  "retirement_reason": "INSUFFICIENT_SYMBOL_DIVERSITY / INSUFFICIENT_TOTAL_TECHNICAL_COVERAGE / DATE_WINDOW_TOO_CLUSTERED",
  "status": "FINAL_HOLDOUT_RETIRED_UNEVALUATED"
}

## Replacement Preregistration
{
  "article_text_policy": "Identical to previous research; no fabricated summaries or changed FinBERT inputs.",
  "dataset_id": "phase14_final_holdout_v2",
  "dedupe_policy": "Existing deterministic FNSPID source id/symbol/date/url/title hash and database URL uniqueness.",
  "end_date": "2023-12-31T23:59:59",
  "event_study": "Event Study V2 unchanged; 1D technical eligibility only in Phase 14.",
  "fingerprint": "7731ecd979ca791ad2c453eb27d3ab51e6a20054515340fbf85f219b0c59d8c0",
  "horizon": "1d",
  "max_scan_rows": 30000,
  "per_symbol_target": 30,
  "price_basis": "Unadjusted Yahoo Finance chart quote.close",
  "price_source": "yahoo_chart_daily",
  "realized_neutral_threshold": 0.001,
  "selection": "Bounded stratified per-symbol FNSPID scan using article, symbol, date, and price availability only.",
  "sentiment_source": "Same FinBERT model/text policy used in Phase 12/13",
  "source_file": "Stock_news/nasdaq_exteral_data.csv",
  "source_name": "FNSPID",
  "source_url": "https://huggingface.co/datasets/Zihan1004/FNSPID/resolve/main/Stock_news/nasdaq_exteral_data.csv",
  "start_date": "2023-01-01T00:00:00",
  "status": "PREREGISTERED_REPLACEMENT_CANDIDATE",
  "symbols": [
    "AAPL",
    "AMZN",
    "GOOGL",
    "NVDA",
    "TSLA"
  ]
}

## Replacement Candidate
{
  "adequacy_passed": false,
  "article_ids": [
    256,
    257,
    258,
    259,
    260,
    261,
    262,
    263,
    234,
    235,
    236,
    237,
    238,
    239,
    240,
    241,
    242,
    243,
    244,
    245,
    246,
    247,
    248,
    249,
    250,
    251,
    252,
    253,
    254,
    255,
    46,
    47,
    48,
    49,
    50,
    41,
    42,
    43,
    44,
    45,
    22,
    23,
    24,
    25,
    26,
    27,
    28,
    29,
    30,
    31,
    32,
    33,
    34,
    35,
    36,
    37,
    38,
    39,
    40,
    20,
    21,
    15,
    16,
    17,
    18,
    19,
    14,
    13,
    8,
    9,
    10,
    11,
    12,
    6,
    7,
    3,
    4,
    5,
    1,
    2
  ],
  "blockers": [
    "INSUFFICIENT_SYMBOL_DIVERSITY",
    "INSUFFICIENT_TOTAL_TECHNICAL_COVERAGE",
    "MISSING_DATE_WINDOW"
  ],
  "candidate_n": 80,
  "cohort_fingerprint": "0b6a02e786542351fac70d45a6547595457701c803b830327f1b75893020f400",
  "coverage_summary": {
    "articles": 80,
    "horizons": {
      "1D": {
        "eligible": 0,
        "no_coverage": 0,
        "unsupported_granularity": 80
      }
    },
    "with_historical_bars": 80,
    "with_instrument": 80
  },
  "dataset_id": "phase14_final_holdout_v2",
  "date_end": null,
  "date_start": null,
  "instruments": [
    "US:AAPL"
  ],
  "locked_at": null,
  "performance_evaluated": false,
  "source_manifest": {
    "checksum_sha256": "063cbfdb230b00a677bc05f229b42cfeb746b26594ac0f01bb730afd671f8c75",
    "per_symbol_counts": {
      "AAPL": 30,
      "AMZN": 0,
      "GOOGL": 0,
      "NVDA": 0,
      "TSLA": 0
    },
    "quota_satisfied": false,
    "requested_symbols": [
      "AAPL",
      "AMZN",
      "GOOGL",
      "NVDA",
      "TSLA"
    ],
    "scan_limit_reached": true,
    "scanned_rows": 30001,
    "subset_path": "data\\research_sources\\fnspid\\subsets\\phase14_final_holdout_v2.csv",
    "written_rows": 30
  },
  "status": "FINAL_HOLDOUT_NOT_READY",
  "symbol_eligible_counts": {},
  "technically_eligible_n": 0
}

## Lock Status
FINAL_HOLDOUT_NOT_READY