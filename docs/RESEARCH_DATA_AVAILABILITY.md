# Research Data Availability

Phase 10 audited the local project data before adding the historical signal evaluation framework.

Phase 11 populated the first real local historical-news cohort from a bounded FNSPID subset.

## Local Runtime Database

The local SQLite database opened successfully at `data/finsent.db`, but the active research tables did not contain historical rows at audit time:

- `news_articles`: 0
- `price_bars`: 0
- `quote_snapshots`: 0
- `sentiment_analysis_runs`: 0
- `event_study_results`: 0
- `signal_runs`: 0

This means Phase 10 cannot truthfully claim a completed real-data historical signal result from the runtime DB without importing real articles and price bars first.

After Phase 11, the local DB contains 50 imported FNSPID articles, 502 yfinance daily research price bars, 20 FinBERT sentiment runs, 40 signal runs, and 40 Event Study V2 result rows for the preliminary AAPL evaluation subset.

## Usable Local Files

`archive/v1/*.NS.csv` contains real NSE daily historical price CSV files. The archive README identifies it as historical NSE stock data through 2023-10-31, with the archive license stored in `archive/LICENSE`.

These files are usable as historical price input after explicit import. Because they are daily bars, they support `1D` Event Study V2 outcomes but not strict `1H` or `4H` intraday outcomes.

## Reference-Only Files

`All_Indian_Stocks_listed_in_nifty500.csv` and `6000 Largest Companies ranked by Market Cap.csv` are company universe/reference files. They are useful for symbol coverage analysis but are not article or price histories by themselves.

## Unusable Local File

`SnP_daily_update.csv` is a Git LFS pointer in this local copy, not the actual US historical price dataset. The importer detects this condition and must not treat pointer text as market data.

## Provider-Gated Sources

Polygon, Marketaux, Gemini, Kite, and optional research model paths remain credential/dependency gated. Phase 10 does not fake provider output when credentials or source files are absent.

Gemini remains unconfigured locally after Phase 11. FinBERT dependencies are available and were used for a controlled 20-article run.
