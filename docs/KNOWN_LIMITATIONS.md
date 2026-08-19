# Known Limitations

## Product

- FinSent is a local Dash application, not a deployed multi-user service.
- Alerts are contextual dashboard items, not persistent notification subscriptions.
- The supported symbol universe is curated and small.
- Signals are explanatory and should not be treated as investment advice.

## Data

- Alpaca Basic/IEX is not consolidated SIP.
- Live market context is focused on US demo symbols.
- Provider responses vary by market hours, entitlements, and current coverage.
- Local SQLite state is machine-specific unless restored from a data bundle.

## ML

- FinBERT can be slow on first load.
- Sentiment confidence is not calibrated price probability.
- The model reads headline/summary text and can miss context outside the available article fields.

## Research

- Phase 16 final evaluation used `N=111`.
- Final eligible symbols were AMZN, NVDA, and TSLA.
- Horizon was 1D only.
- No profitability, transaction-cost, or execution simulation was performed.
- V2.0 underperformed V1 on strict and balanced accuracy in the locked final cohort.

## Infrastructure

- SQLite is local and process-bound.
- Cache and diagnostics are process-local.
- No Redis, Celery, Kafka, or distributed worker architecture is implemented.
- No DB schema v3 exists.

## Demo

- Live results depend on internet, credentials, market hours, and provider availability.
- If live providers fail, use offline/local research mode and the Research page.
