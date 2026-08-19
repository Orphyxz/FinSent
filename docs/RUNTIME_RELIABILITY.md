# FinSent Runtime Reliability

## Refresh Flow

Dashboard callbacks use a shared process-local dashboard state cache. A refresh builds one normalized state from provider/cache data, SQLite rows, catalyst analysis, market context, and signal metadata. Overlapping callbacks for the same selection reuse that state for a short TTL instead of rebuilding the full workspace.

## Cache Policy

- Quote cache: `QUOTE_CACHE_TTL_SECONDS`, default 10 seconds.
- Price history cache: `PRICE_HISTORY_CACHE_TTL_SECONDS`, default 60 seconds.
- News cache: `NEWS_CACHE_TTL_SECONDS`, default 60 seconds.
- Dashboard state cache: `DASHBOARD_STATE_CACHE_TTL_SECONDS`, default 5 seconds.
- Market-context bars cache: process-local, default 300 seconds inside `MarketContextService`.

Provider cache entries are keyed by service and symbol/window. Market-context benchmark bars are keyed by ticker, date window, and interval so SPY/QQQ/sector ETFs are reused across symbols.

## FinBERT Lifecycle

FinBERT is lazy by default. The analyzer exposes:

- `UNINITIALIZED`
- `LOADING`
- `READY`
- `ERROR`

Model and tokenizer loading are protected by a process-local lock and shared by model name. `FINSENT_FINBERT_WARMUP=true` can initialize FinBERT when the analyzer is constructed. Warm-up failure is reported through diagnostics and does not stop the dashboard.

## Provider Health

Provider health is normalized per provider/service:

- configured
- state
- last success
- last failure
- latency
- success/failure counts
- consecutive failures
- failure category
- rate-limit flag
- fallback flag

Unconfigured providers are not treated as outages.

## Retries And Timeouts

Network calls use finite provider timeouts. Router retries are bounded by `PROVIDER_RETRY_COUNT` and apply only to timeout/network-style transient failures. Authentication, entitlement, bad request, no-data, and malformed response failures are not blindly retried. Rate-limit responses are categorized separately for diagnostics.

## Stale Fallback

Fresh cache hits are labeled `CACHED`. Provider failure with an older cache entry is labeled `STALE_CACHE` and surfaced as stale/latest-available data, never as live data.

## Persistence Policy

Articles, article-instrument links, quotes, and bars use existing idempotency keys. Live Signal V2 persistence now uses a deterministic live input fingerprint, so identical quote/bar/article input reuses the previous live run. V1 signal snapshots update/reuse the same quote-ingestion row instead of appending duplicates for the same input.

Provider audit and data-quality rows are written for real provider attempts. Cache reads remain visible through runtime diagnostics rather than creating extra audit rows.

## SQLite Behavior

Runtime writes use explicit commits and rollback on exceptions. Sessions are scoped to the operation and closed by context manager. SQLite remains local and process-bound; no distributed lock manager or worker queue is introduced.

## Market Context Alignment

Market-relative and sector-relative returns use timestamp-aligned common windows. Missing or offset bars result in partial/insufficient quality rather than silently comparing mismatched first-to-last windows.

## Diagnostics

The dashboard includes a compact System Status panel with:

- active market provider
- active news provider
- provider state
- cache hit rate
- FinBERT state
- DB health and schema
- last refresh age
- refresh duration
- latest safe runtime error

Diagnostics are process-local and not persisted.

## Security

Startup and runtime diagnostics never print API keys, secrets, or authorization headers. `.env`, datasets, DBs, caches, model files, and generated research artifacts remain excluded by git policy.

## Known Limitations

- Process-local cache and diagnostics only.
- SQLite is local and not a production multi-writer database.
- Dash runs as a local/development server.
- No Redis, Celery, Kafka, background queue, or distributed synchronization.
- Alpaca IEX is not SIP.
- Market context is US-symbol focused and uses curated sector ETF mapping.
- First unseen FinBERT inference can still be synchronous unless warm-up is enabled.

## Troubleshooting

- No live price: check Market Data provider status.
- No current news: check News provider status/fallback.
- FinBERT unavailable: check research dependencies/model status.
- Compare partial: inspect per-symbol provider state.
- Market Context unavailable: inspect SPY/sector ETF provider status.
