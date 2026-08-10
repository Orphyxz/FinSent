# Provider Reliability

Phase 4 hardens the Phase 3 provider routers. It does not alter Signal Engine V1 or event-study behavior.

## Active Network Call Audit

| Path | Timeout | Retry before Phase 4 | Rate limit handling before Phase 4 | Empty/invalid handling before Phase 4 | Provenance before Phase 4 |
|---|---:|---|---|---|---|
| Polygon quote snapshot | 15s | internal quote fallback only | generic request exception | unavailable quote | provider only |
| Polygon last trade | 15s | none | generic request exception | ignored fallback row | note says last trade |
| Polygon previous close | 15s | none | generic request exception | ignored fallback row | note says previous close |
| Polygon bars | 15s | none | generic request exception | empty frame | provider only |
| Polygon news | 15s | router fallback only | HTTP errors bubbled | empty/exception | provider only |
| Kite quote | 15s | none | generic request exception | unavailable quote | provider only |
| Kite instruments/bars | 15-30s | none | generic request exception | empty frame | provider only |
| Marketaux news | 15s | symbol query then company query | HTTP errors bubbled | empty/exception | provider only |
| Gemini search fallback | Gemini timeout setting | none | client exception -> no articles | empty list | hidden under fallback web |
| Alpaca news fallback | 20s | none | request exception -> no articles | empty list | hidden under fallback web |
| yfinance news fallback | library behavior | none | exception -> no articles | empty list | hidden under fallback web |
| Yahoo HTML fallback | 20s | tries candidate URLs | request exception -> next URL | empty list | hidden under fallback web |

## Timeout Policy

All active direct HTTP requests use finite timeouts.

Defaults remain provider-local and conservative:

- Polygon: 15 seconds.
- Kite: 15 seconds; instruments endpoint at least 30 seconds.
- Marketaux: 15 seconds.
- Yahoo fallback: 20 seconds.
- Gemini: `GEMINI_TIMEOUT_SECONDS`.

Phase 4 adds testable retry and freshness settings:

- `PROVIDER_RETRY_COUNT`
- `PROVIDER_RETRY_BACKOFF_SECONDS`
- `QUOTE_FRESH_SECONDS`
- `QUOTE_AGING_SECONDS`
- `NEWS_FRESH_MINUTES`
- `NEWS_AGING_MINUTES`

## Retry Policy

Routers retry transient failures only:

- timeout
- network interruption
- selected HTTP 5xx responses, classified as network/transient

Routers do not retry:

- unconfigured providers
- authentication failures
- permanent 4xx failures
- invalid responses
- unsupported symbols
- no-data cases

Retry count is small by default: one retry. Backoff is bounded and injectable in tests.

## Rate-Limit Behavior

HTTP `429` is classified as `RATE_LIMIT`.

`Retry-After` is parsed when present and preserved as safe metadata. The router does not bypass provider limits, rotate credentials, or aggressively retry rate-limited requests.

Fallback may proceed where configured.

## Cache Behavior

Phase 4 adds a small in-memory TTL cache used by provider routers.

Cache keys include:

- operation
- symbol
- requested news limit
- historical bar interval/window where relevant

Cache entries preserve:

- original provider
- leaf provider
- data mode
- source timestamp
- fetch timestamp
- quality assessment

Cache TTLs:

- quotes: `QUOTE_CACHE_TTL_SECONDS`
- news: `NEWS_CACHE_TTL_SECONDS`
- historical bars: `PRICE_HISTORY_CACHE_TTL_SECONDS`

`from_cache=True` is always explicit.

## Stale-Cache Fallback

When a live provider request fails and an expired cached entry exists, the router may return stale cached data as `STALE`.

The attempt trace records:

- live provider failure
- stale cache selected

Stale cache is not labeled as fresh live data.

## Provider Health Model

`ProviderHealthRegistry` stores current-session health only.

Tracked fields:

- provider
- service
- configured
- last status
- last successful fetch
- last failure category
- last checked
- recent fallback usage

This is intended for debugging, future UI display, and demo transparency. It is not a persistent monitoring platform.

## Provenance

`ProviderResult` now carries:

- top-level route provider
- leaf provider
- data mode
- freshness
- data quality
- fallback-used flag
- attempt trace

Examples:

- provider: `polygon`, leaf provider: `polygon/snapshot`, mode: `LIVE`
- provider: `polygon`, leaf provider: `polygon/previous_close`, mode: `PREVIOUS_CLOSE`
- provider: `fallback_web`, leaf provider: `yahoo_html`, mode: `SCRAPED`
- provider: `fallback_web`, leaf provider: `gemini_search`, mode: `SEARCH_DERIVED`

## Limitations

- Retry happens at the router call boundary; provider-internal fallbacks may still swallow some lower-level exceptions.
- No persistent health table exists yet.
- No complete raw API responses are stored.
- No distributed cache or Redis is introduced.
