# Final Holdout Preregistration

Status: `FINAL_HOLDOUT_LOCKED`

Dataset id: `phase13_final_holdout_v1`
Fingerprint: `b7a50a311a5ff7f896b185516cec2b2fffc874b370e69a3a4d1c1469b30637b9`

This cohort is reserved for a later explicit final evaluation. Phase 13 may check technical price coverage only.

```json
{
  "article_cap": 150,
  "data_availability_note": "The same five Phase 12 symbols were requested. The smaller All_external.csv source yielded no post-2020-06-15 rows in a bounded scan, and the larger Nasdaq FNSPID source is too large to exhaustively scan for all five symbols in Phase 13. AAPL-only locking is therefore a documented data-availability/feasibility limitation, not symbol cherry-picking.",
  "dataset_id": "phase13_final_holdout_v1",
  "end_date": "2023-12-13T23:59:59",
  "fingerprint": "b7a50a311a5ff7f896b185516cec2b2fffc874b370e69a3a4d1c1469b30637b9",
  "horizon": "1d",
  "locked_symbols": [
    "AAPL"
  ],
  "markets": [
    "US"
  ],
  "max_scan_rows": 100000,
  "per_symbol_target": 30,
  "price_basis": "Unadjusted Yahoo Finance chart quote.close",
  "price_source": "yahoo_chart_daily",
  "requested_symbols": [
    "AAPL",
    "AMZN",
    "GOOGL",
    "NVDA",
    "TSLA"
  ],
  "selection_method": "Bounded deterministic FNSPID scan using article and price availability only; no model-performance criteria.",
  "sentiment_source": "FinBERT only; not run on the final holdout in Phase 13",
  "source_file": "Stock_news/nasdaq_exteral_data.csv",
  "source_name": "FNSPID",
  "source_url": "https://huggingface.co/datasets/Zihan1004/FNSPID/resolve/main/Stock_news/nasdaq_exteral_data.csv",
  "start_date": "2023-11-01T00:00:00",
  "status": "FINAL_HOLDOUT_LOCKED"
}
```

Forbidden in Phase 13: Signal V1/V2/V2.1 accuracy, balanced accuracy, confusion matrices, realized-direction summaries, and candidate filtering.

## Phase 14 Retirement Note

The Phase 13 AAPL-only holdout is preserved but structurally inadequate for final testing under the Phase 14 adequacy policy. It remains unevaluated.
