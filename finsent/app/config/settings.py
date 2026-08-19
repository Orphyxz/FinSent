from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


def _env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, *, minimum: int | None = None) -> int:
    raw = os.getenv(name)
    try:
        value = int(raw) if raw not in {None, ""} else default
    except ValueError:
        value = default
    if minimum is not None:
        value = max(value, minimum)
    return value


def _env_float(name: str, default: float, *, minimum: float | None = None) -> float:
    raw = os.getenv(name)
    try:
        value = float(raw) if raw not in {None, ""} else default
    except ValueError:
        value = default
    if minimum is not None:
        value = max(value, minimum)
    return value


@dataclass(slots=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///data/finsent.db")
    news_source_base_url: str = os.getenv("NEWS_SOURCE_BASE_URL", "https://finance.yahoo.com")
    sentiment_provider: str = os.getenv("SENTIMENT_PROVIDER", "finbert")
    signal_engine_version: str = os.getenv("SIGNAL_ENGINE_VERSION", "v1")
    news_discovery_provider: str = os.getenv("NEWS_DISCOVERY_PROVIDER", "gemini")
    live_data_provider: str = os.getenv("LIVE_DATA_PROVIDER", "auto")
    polygon_api_key: str = os.getenv("POLYGON_API_KEY", "")
    polygon_base_url: str = os.getenv("POLYGON_BASE_URL", "https://api.polygon.io")
    marketaux_api_token: str = os.getenv("MARKETAUX_API_TOKEN", "")
    marketaux_base_url: str = os.getenv("MARKETAUX_BASE_URL", "https://api.marketaux.com/v1")
    kite_api_key: str = os.getenv("KITE_API_KEY", "")
    kite_api_secret: str = os.getenv("KITE_API_SECRET", "")
    kite_access_token: str = os.getenv("KITE_ACCESS_TOKEN", "")
    kite_base_url: str = os.getenv("KITE_BASE_URL", "https://api.kite.trade")
    alpaca_api_key: str = os.getenv("ALPACA_API_KEY", "")
    alpaca_api_secret: str = os.getenv("ALPACA_API_SECRET", "")
    alpaca_data_base_url: str = os.getenv("ALPACA_DATA_BASE_URL", "https://data.alpaca.markets")
    alpaca_feed: str = os.getenv("ALPACA_FEED", "iex")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    gemini_timeout_seconds: int = _env_int("GEMINI_TIMEOUT_SECONDS", 20, minimum=1)
    llm_analysis_limit: int = _env_int("LLM_ANALYSIS_LIMIT", 5, minimum=0)
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-5-mini")
    gemini_use_search_grounding: bool = _env_bool("GEMINI_USE_SEARCH_GROUNDING", "true")
    default_ticker: str = os.getenv("DEFAULT_TICKER", "AAPL")
    default_news_limit: int = _env_int("DEFAULT_NEWS_LIMIT", 20, minimum=0)
    default_return_window_minutes: int = _env_int("DEFAULT_RETURN_WINDOW_MINUTES", 60, minimum=1)
    default_price_interval: str = os.getenv("DEFAULT_PRICE_INTERVAL", "15m")
    signal_lookback_bars: int = _env_int("SIGNAL_LOOKBACK_BARS", 16, minimum=1)
    live_refresh_interval_ms: int = _env_int("LIVE_REFRESH_INTERVAL_MS", 15000, minimum=5000)
    dashboard_state_cache_ttl_seconds: int = _env_int("DASHBOARD_STATE_CACHE_TTL_SECONDS", 5, minimum=1)
    live_refresh_max_age_minutes: int = _env_int("LIVE_REFRESH_MAX_AGE_MINUTES", 2, minimum=1)
    live_price_max_age_minutes: int = _env_int("LIVE_PRICE_MAX_AGE_MINUTES", 1440, minimum=1)
    live_news_max_age_minutes: int = _env_int("LIVE_NEWS_MAX_AGE_MINUTES", 1440, minimum=1)
    quote_cache_ttl_seconds: int = _env_int("QUOTE_CACHE_TTL_SECONDS", 10, minimum=1)
    price_history_cache_ttl_seconds: int = _env_int("PRICE_HISTORY_CACHE_TTL_SECONDS", 60, minimum=1)
    news_cache_ttl_seconds: int = _env_int("NEWS_CACHE_TTL_SECONDS", 60, minimum=1)
    analysis_cache_ttl_seconds: int = _env_int("ANALYSIS_CACHE_TTL_SECONDS", 86400, minimum=1)
    provider_retry_count: int = _env_int("PROVIDER_RETRY_COUNT", 1, minimum=0)
    provider_retry_backoff_seconds: float = _env_float("PROVIDER_RETRY_BACKOFF_SECONDS", 0.1, minimum=0.0)
    quote_fresh_seconds: int = _env_int("QUOTE_FRESH_SECONDS", 60, minimum=1)
    quote_aging_seconds: int = _env_int("QUOTE_AGING_SECONDS", 900, minimum=1)
    news_fresh_minutes: int = _env_int("NEWS_FRESH_MINUTES", 360, minimum=1)
    news_aging_minutes: int = _env_int("NEWS_AGING_MINUTES", 1440, minimum=1)
    default_quote_currency_us: str = os.getenv("DEFAULT_QUOTE_CURRENCY_US", "USD")
    default_quote_currency_in: str = os.getenv("DEFAULT_QUOTE_CURRENCY_IN", "INR")
    model_name: str = os.getenv("MODEL_NAME", "ProsusAI/finbert")
    finbert_warmup: bool = _env_bool("FINSENT_FINBERT_WARMUP", "false")


settings = Settings()
