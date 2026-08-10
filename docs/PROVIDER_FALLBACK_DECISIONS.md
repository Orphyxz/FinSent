# Provider Fallback Decisions

Phase 4 reviews fallback options for reliability and data integrity. The goal is not to always show a number; it is to preserve trustworthy provenance.

## Market Fallbacks

| Fallback | Decision | Rationale |
|---|---|---|
| Polygon snapshot -> last trade -> previous close | ACTIVE | Already provider-internal, preserves quote note, now exposed as leaf provider modes. Previous close is not treated as live. |
| US Polygon -> legacy yfinance market service | DEFERRED | yfinance can improve availability, but current legacy market code has different semantics and weaker explicit provider status/provenance. Activating it may mislead users into comparing provider-grade and scraped/library data as equivalent. |
| US Polygon -> Alpaca market service | DEFERRED | Requires Alpaca credentials and lives in deprecated `market_data.py`. It needs adapter tests and provenance normalization before activation. |
| NSE/BSE Kite -> local archive CSV | DEFERRED | Archive data is historical/local, not a live quote substitute. Safe for research import, not active quote fallback. |
| NSE/BSE Kite -> yfinance `.NS` / `.BO` | DEFERRED | Could improve availability but needs a dedicated normalized provider adapter, freshness policy, and reliability tests. |

Current active market chains remain:

- US: Polygon -> unavailable.
- NSE/BSE: Kite -> unavailable.

## News Fallbacks

| Fallback | Decision | Rationale |
|---|---|---|
| US Polygon News -> fallback web | ACTIVE | Preserves availability with explicit fallback/leaf provenance and lower data-quality score. |
| NSE/BSE Marketaux -> fallback web | ACTIVE | Preserves Indian-market news availability when Marketaux is unconfigured or empty. |
| Gemini Search inside fallback web | ACTIVE | Can provide timely discovered URLs when configured. Marked as `SEARCH_DERIVED`, not provider-grade news. |
| Alpaca News inside fallback web | ACTIVE | Structured API source when configured. Marked as `LIVE` leaf source `alpaca_news`. |
| yfinance News inside fallback web | ACTIVE | Useful library fallback but metadata can vary. Marked as `SCRAPED`-quality fallback. |
| Yahoo HTML inside fallback web | ACTIVE | Last-resort source. Marked as `SCRAPED`; selector breakage returns no success. |

Fallback order currently remains:

1. Gemini Search
2. Alpaca News
3. yfinance News
4. Yahoo HTML

This order favors freshness first, but data quality is explicitly lowered for search-derived and scraped paths.

## Historical Data Sources

| Source | Decision | Quality | Notes |
|---|---|---|---|
| `archive/v1/*.csv` | ACTIVE FOR OFFLINE IMPORT | USABLE/PARTIAL | Large NSE historical archive. Timestamp normalized to naive UTC. Completeness varies by file and is not yet scored by symbol/date coverage. |
| `SnP_daily_update.csv` | BROKEN IN LOCAL COPY | BROKEN | Current file is a Git LFS pointer. Guard rejects it before parsing. |
| `All_Indian_Stocks_listed_in_nifty500.csv` | ACTIVE REFERENCE DATA | PARTIAL | Useful universe/reference file, not a live price source. |
| `6000 Largest Companies ranked by Market Cap.csv` | ACTIVE REFERENCE DATA | PARTIAL | Useful US universe/reference file, not a live price source. |
| Provider bars from Polygon/Kite | ACTIVE LIVE/HISTORICAL PROVIDER | USABLE WHEN VALID | Routed through `MarketDataRouter` and validated before acceptance. |

## Remaining Decisions

- Build explicit yfinance/Alpaca market adapters only if later phases need higher live availability.
- Add persistent provider-run history before final research reporting.
- Add symbol/date-range completeness checks for local historical datasets before backtesting.
