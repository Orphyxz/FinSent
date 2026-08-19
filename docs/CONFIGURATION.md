# Configuration Reference

Use a root `.env` file for local secrets and settings. Never commit real values.

## Alpaca

| Variable | Required? | Default | Purpose |
|---|---|---|---|
| `ALPACA_API_KEY` | Live US demo | empty | Alpaca key id. |
| `ALPACA_API_SECRET` | Live US demo | empty | Alpaca secret key. |
| `ALPACA_DATA_BASE_URL` | No | `https://data.alpaca.markets` | Alpaca market-data API base. |
| `ALPACA_FEED` | No | `iex` | Alpaca feed, normally IEX for Basic. |

## Polygon

| Variable | Required? | Default | Purpose |
|---|---|---|---|
| `POLYGON_API_KEY` | Optional | empty | US market/news fallback. |
| `POLYGON_BASE_URL` | No | `https://api.polygon.io` | Polygon API base. |

## Kite

| Variable | Required? | Default | Purpose |
|---|---|---|---|
| `KITE_API_KEY` | Optional | empty | Kite Connect key. |
| `KITE_API_SECRET` | Optional | empty | Kite secret for manual workflows. |
| `KITE_ACCESS_TOKEN` | Optional | empty | Kite access token for NSE/BSE data. |
| `KITE_BASE_URL` | No | `https://api.kite.trade` | Kite API base. |

## Marketaux

| Variable | Required? | Default | Purpose |
|---|---|---|---|
| `MARKETAUX_API_TOKEN` | Optional | empty | News fallback token. |
| `MARKETAUX_BASE_URL` | No | `https://api.marketaux.com/v1` | Marketaux API base. |

## Gemini / OpenAI Compatibility

| Variable | Required? | Default | Purpose |
|---|---|---|---|
| `GEMINI_API_KEY` | Optional | empty | Optional legacy/compatibility Gemini analyzer or fallback search path. |
| `GEMINI_MODEL` | No | `gemini-2.5-flash` | Gemini model id. |
| `GEMINI_TIMEOUT_SECONDS` | No | `20` | Gemini request timeout. |
| `GEMINI_USE_SEARCH_GROUNDING` | No | `true` | Enables Gemini search grounding where used. |
| `LLM_ANALYSIS_LIMIT` | No | `5` | Maximum configured LLM article analyses per refresh where applicable. |
| `OPENAI_API_KEY` | No | empty | OpenAI analyzer is a stub in this project. |
| `OPENAI_MODEL` | No | `gpt-5-mini` | Stored compatibility setting only. |

## Sentiment And Signals

| Variable | Required? | Default | Purpose |
|---|---|---|---|
| `SENTIMENT_PROVIDER` | No | `finbert` | Live analyzer selection: `finbert`, `gemini`, or `openai` stub. |
| `MODEL_NAME` | No | `ProsusAI/finbert` | FinBERT model name. |
| `FINSENT_FINBERT_WARMUP` | No | `false` | Load FinBERT when analyzer is created. |
| `SIGNAL_ENGINE_VERSION` | No | `v1` | Compatibility setting; dashboard displays V1 and V2 live outputs. |
| `SIGNAL_LOOKBACK_BARS` | No | `16` | Recent bar lookback for live signal context. |

## Dashboard Refresh

| Variable | Required? | Default | Purpose |
|---|---|---|---|
| `DEFAULT_TICKER` | No | `AAPL` | Default ticker setting. |
| `DEFAULT_NEWS_LIMIT` | No | `20` | News request limit. |
| `DEFAULT_RETURN_WINDOW_MINUTES` | No | `60` | Legacy event-frame window. |
| `DEFAULT_PRICE_INTERVAL` | No | `15m` | Price bar interval. |
| `LIVE_REFRESH_INTERVAL_MS` | No | `15000` | Dash refresh interval, lower bounded at 5000 ms. |
| `DASHBOARD_STATE_CACHE_TTL_SECONDS` | No | `5` | Process-local dashboard-state cache TTL. |
| `LIVE_REFRESH_MAX_AGE_MINUTES` | No | `2` | Recent refresh freshness boundary. |
| `LIVE_PRICE_MAX_AGE_MINUTES` | No | `1440` | Maximum age before live price context is considered unavailable/stale. |
| `LIVE_NEWS_MAX_AGE_MINUTES` | No | `1440` | Maximum age before live news context is considered unavailable/stale. |

## Provider Cache And Quality

| Variable | Required? | Default | Purpose |
|---|---|---|---|
| `QUOTE_CACHE_TTL_SECONDS` | No | `10` | Quote cache TTL. |
| `PRICE_HISTORY_CACHE_TTL_SECONDS` | No | `60` | Bars cache TTL. |
| `NEWS_CACHE_TTL_SECONDS` | No | `60` | News cache TTL. |
| `ANALYSIS_CACHE_TTL_SECONDS` | No | `86400` | Article analysis reuse TTL. |
| `PROVIDER_RETRY_COUNT` | No | `1` | Bounded transient retry count. |
| `PROVIDER_RETRY_BACKOFF_SECONDS` | No | `0.1` | Retry backoff. |
| `QUOTE_FRESH_SECONDS` | No | `60` | Quote live freshness boundary. |
| `QUOTE_AGING_SECONDS` | No | `900` | Quote latest-available boundary. |
| `NEWS_FRESH_MINUTES` | No | `360` | Fresh news boundary. |
| `NEWS_AGING_MINUTES` | No | `1440` | Aging news boundary. |

## Local Defaults

| Variable | Required? | Default | Purpose |
|---|---|---|---|
| `NEWS_SOURCE_BASE_URL` | No | `https://finance.yahoo.com` | Base URL used by legacy/fallback news paths. |
| `NEWS_DISCOVERY_PROVIDER` | No | `gemini` | Compatibility setting for fallback discovery paths. |
| `LIVE_DATA_PROVIDER` | No | `auto` | Compatibility setting; routers decide active provider order. |
| `DEFAULT_QUOTE_CURRENCY_US` | No | `USD` | Display currency for US quotes. |
| `DEFAULT_QUOTE_CURRENCY_IN` | No | `INR` | Display currency for India quotes. |

## Database

| Variable | Required? | Default | Purpose |
|---|---|---|---|
| `DATABASE_URL` | No | `sqlite:///data/finsent.db` | Local SQLAlchemy database URL. |

## Logging

| Variable | Required? | Default | Purpose |
|---|---|---|---|
| `FINSENT_LOG_LEVEL` | No | `INFO` | Local logging verbosity. |
