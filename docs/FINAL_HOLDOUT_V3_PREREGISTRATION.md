# Final Holdout V3 Preregistration

{
  "acquisition_symbols": [
    "AAPL",
    "AMZN",
    "NVDA",
    "TSLA"
  ],
  "availability_end": "2023-12-31T23:59:59",
  "availability_start": "2023-01-01T00:00:00",
  "cutoff_after": "2020-06-15T23:59:59",
  "dataset_id": "phase15_final_holdout_v3",
  "dedupe_policy": "FNSPID source id/symbol/date/url/title hash plus database URL uniqueness.",
  "event_horizon": "1d",
  "fingerprint": "9d166c563017175dfb4f8eaef3e65ca5a68beafb493e1f4fa265511d6c5a8773",
  "minimum_per_symbol_eligible": 20,
  "minimum_symbols": 3,
  "minimum_total_eligible": 90,
  "per_symbol_quota": 40,
  "price_basis": "unadjusted quote.close",
  "price_buffer_days_after": 10,
  "price_buffer_days_before": 30,
  "price_source": "yahoo_chart_daily",
  "realized_neutral_threshold": 0.001,
  "selection_rule": "Earliest 90-day future window with >=3 supported symbols, >=20 candidate articles per represented symbol, and >=90 total candidate articles; tie-break by represented symbol count then balance.",
  "sentiment_model_for_phase16": "FinBERT, same frozen model/text policy as development",
  "source_file": "Stock_news/nasdaq_exteral_data.csv",
  "source_name": "FNSPID",
  "source_url": "https://huggingface.co/datasets/Zihan1004/FNSPID/resolve/main/Stock_news/nasdaq_exteral_data.csv",
  "target_symbols": [
    "AAPL",
    "AMZN",
    "GOOGL",
    "NVDA",
    "TSLA"
  ],
  "window_days": 90,
  "within_symbol_sampling": "Chronological evenly spaced sample across the selected window if records exceed quota."
}