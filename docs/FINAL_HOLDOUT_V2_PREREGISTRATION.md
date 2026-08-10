# Final Holdout V2 Preregistration

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

No performance values may influence this selection.

## Phase 15 Supersession

V2 remains not ready. V3 uses a source-layout-aware acquisition strategy and does not evaluate performance.
