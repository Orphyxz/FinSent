# FinSent Market Universe

## Supported Registry

FinSent ships with a curated, eagerly loaded metadata registry containing:

- 206 US instruments across all 11 GICS sectors.
- 149 primary Indian NSE instruments covering NIFTY 50, Nifty Next 50 and liquid mid-cap names.
- 20 BSE compatibility records for large caps that need explicit BSE routing.

Every ticker was checked against Yahoo chart data when added. Tata Motors trades as `TMPV` (Passenger Vehicles) and `TMCV` (Commercial Vehicles) after its 2025 demerger, and LTIMindtree as `LTM`. Berkshire Hathaway is omitted because Alpaca and Yahoo spell its ticker differently (`BRK.B` vs `BRK-B`).

Market prices, bars, news, FinBERT inference, signals, catalysts, and benchmark context are not preloaded for this universe. They are requested only for selected instruments.

## Canonical Symbols

The application UI uses clean canonical tickers such as `AAPL`, `RELIANCE`, and `TCS`. Internally, an instrument record carries identity, company, market, exchange, currency, sector, listing exchange, and provider mappings. The UI displays labels such as `AAPL - Apple | US` and `RELIANCE - Reliance Industries Ltd. | NSE`.

## Provider Mappings

Provider formatting is centralized in `SymbolRecord.symbol_for()` and registry resolution:

| Market | Canonical | Alpaca/Polygon | Kite | Yahoo fallback |
|---|---|---|---|---|
| US | `AAPL` | `AAPL` | not used | `AAPL` |
| NSE | `RELIANCE` | not used | `NSE:RELIANCE` | `RELIANCE.NS` |
| BSE | exchange-specific ticker | not used | `BSE:<ticker>` | `<ticker>.BO` |

Provider suffixes are not exposed as the primary user-facing identity. `.NS` and `.BO` are used only for the Yahoo fallback mapping and are not assumed for Kite.

## Currency Logic

US records use `USD` and are formatted with `$`. NSE and BSE records use `INR` and are formatted with the Indian rupee symbol. Currency formatting is centralized in the dashboard view model rather than repeated in callbacks.

## Market Filters and Search

The global filter supports ALL, US, and INDIA. INDIA includes the primary NSE universe and exchange-aware Indian records. The selector searches the local registry by ticker or company name and remains keyboard accessible through the Dash dropdown. Search does not call a provider or start market/news downloads.

## Static Fallback Registry

The bundled registry is the reliable default universe when provider-side discovery is unavailable. It is deliberately curated rather than an exhaustive exchange dump, which keeps startup and search lightweight and avoids presenting unverified symbols merely to increase the count.

## Dynamic Discovery

Dynamic external instrument discovery is not implemented in Phase 23. New supported instruments should be added to the centralized registry with verified provider mappings, market, exchange, currency, and sector metadata.

## Benchmark Context

US Market Context continues to use SPY, QQQ, and mapped US sector ETFs under the existing Phase 19 semantics. Indian equities are never compared against those US benchmarks. Until a reliable Indian benchmark data path and methodology are approved, the dashboard reports `Indian benchmark context unavailable` while retaining any independently available quote, sentiment, signal, and catalyst capabilities.

## Unsupported and Partial Cases

- A symbol absent from the registry is treated as unsupported instead of being guessed.
- A configured symbol may have price data but no recent news, or news but no usable quote.
- Kite without a valid session reports an explicit unavailable state and does not claim live data.
- Missing sector benchmark, bars, or news produces a capability-aware empty state; it does not crash the dashboard or invalidate available features.
