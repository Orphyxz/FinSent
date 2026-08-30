from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from time import perf_counter
from typing import Callable

import pandas as pd

from finsent.app.config.settings import settings
from finsent.app.services.market_providers import (
    AlpacaMarketDataProvider,
    KiteMarketDataProvider,
    PolygonMarketDataProvider,
    QuoteSnapshot,
    UnavailableMarketProvider,
    YahooHistoricalMarketDataProvider,
    is_usable_quote_snapshot,
)
from finsent.app.services.news_providers import (
    AlpacaNewsProvider,
    CuratedWebNewsProvider,
    MarketauxNewsProvider,
    NormalizedNewsArticle,
    PolygonNewsProvider,
    normalize_news_limit,
)
from finsent.app.services.provider_contracts import (
    ActiveHistoricalDataProvider,
    ActiveMarketDataProvider,
    ActiveNewsProvider,
    ProviderAttempt,
    ProviderCandidate,
    ProviderFailureCategory,
    ProviderResult,
    attempt_from_status,
    classify_exception,
    status_from_category,
)
from finsent.app.services.provider_status import DataSourceState, ProviderStatus
from finsent.app.services.provider_reliability import (
    CacheEntry,
    DataMode,
    ProviderHealthRegistry,
    ProviderTTLCache,
    assess_bars_quality,
    assess_news_quality,
    assess_quote_quality,
    call_with_retries,
    data_mode_for_quote,
    leaf_provider_for_quote,
    retry_after_seconds,
    validate_bars_frame,
    validate_news_articles,
    validate_quote_snapshot,
)
from finsent.app.services.symbol_registry import SymbolRecord
from finsent.app.utils.logging import safe_log_message


MARKET_DATA_SERVICE = "market_quote"
HISTORICAL_DATA_SERVICE = "market_bars"
NEWS_SERVICE = "news"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _duration_ms(started_at: float) -> int:
    return int((perf_counter() - started_at) * 1000)


def _status_code(exc: Exception) -> int | None:
    value = getattr(getattr(exc, "response", None), "status_code", None)
    return int(value) if isinstance(value, int) else None


def _quote_timestamp(quote: QuoteSnapshot | None) -> datetime | None:
    return quote.market_timestamp if quote is not None else None


def _empty_bars() -> pd.DataFrame:
    return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])


def _coerce_data_mode(value: object, fallback: DataMode) -> DataMode:
    if isinstance(value, DataMode):
        return value
    try:
        return DataMode(str(value))
    except (TypeError, ValueError):
        return fallback


@dataclass(slots=True)
class MarketDataRouter:
    candidates: list[ProviderCandidate] | None = None
    cache: ProviderTTLCache | None = None
    health: ProviderHealthRegistry | None = None
    clock: Callable[[], datetime] | None = None
    sleep: Callable[[float], None] | None = None

    def __post_init__(self) -> None:
        if self.candidates is None:
            self.candidates = default_market_candidates()
        if self.cache is None:
            self.cache = ProviderTTLCache(clock=self.clock, name="market_provider")
        if self.health is None:
            self.health = ProviderHealthRegistry(clock=self.clock)

    def fetch_quote(self, symbol: SymbolRecord) -> ProviderResult[QuoteSnapshot]:
        attempts: list[ProviderAttempt] = []
        unsupported_seen = False
        cache_key = ("quote", symbol.internal_id)
        cached = self.cache.get(cache_key, settings.quote_cache_ttl_seconds) if self.cache is not None else None
        if cached is not None:
            quote = cached.data
            mode = DataMode.CACHED
            quality = assess_quote_quality(quote, provider=cached.provider, mode=mode, fetched_at=_now())  # type: ignore[arg-type]
            status = ProviderStatus.degraded(cached.provider, MARKET_DATA_SERVICE, "Quote returned from in-memory cache.", source_timestamp=cached.source_timestamp)
            return ProviderResult(
                data=quote,  # type: ignore[arg-type]
                status=status,
                provider=cached.provider,
                service=MARKET_DATA_SERVICE,
                source_timestamp=cached.source_timestamp,
                fetched_at=_now(),
                from_cache=True,
                fallback_used=False,
                attempts=[attempt_from_status(status, selected=True)],
                message=status.message,
                leaf_provider=cached.leaf_provider,
                data_mode=mode,
                freshness=quality.freshness,
                quality=quality,
            )

        for candidate in self.candidates or []:
            if not candidate.supports_exchange(symbol.exchange):
                unsupported_seen = True
                continue
            if not candidate.configured():
                status = ProviderStatus.unconfigured(candidate.provider, MARKET_DATA_SERVICE, candidate.unconfigured_message)
                attempts.append(attempt_from_status(status, category=ProviderFailureCategory.UNCONFIGURED))
                self.health.record(provider=candidate.provider, service=MARKET_DATA_SERVICE, configured=False, status=status.status, failure_category=ProviderFailureCategory.UNCONFIGURED)
                continue

            provider = candidate.factory()
            started_at = perf_counter()
            try:
                quote = call_with_retries(
                    lambda: provider.fetch_quote_snapshot(symbol),  # type: ignore[attr-defined]
                    sleep=self.sleep or (lambda _: None),
                )
            except Exception as exc:
                category = classify_exception(exc)
                latency = _duration_ms(started_at)
                status = status_from_category(candidate.provider, MARKET_DATA_SERVICE, category, f"Quote request failed: {safe_log_message(exc)}")
                attempts.append(attempt_from_status(status, category=category, duration_ms=latency))
                self.health.record(provider=candidate.provider, service=MARKET_DATA_SERVICE, configured=True, status=status.status, failure_category=category, latency_ms=latency, status_code=_status_code(exc))
                continue

            status = quote.provider_status or ProviderStatus.unavailable(candidate.provider, MARKET_DATA_SERVICE, quote.note)
            validation_reasons = validate_quote_snapshot(quote)
            if is_usable_quote_snapshot(quote) and not validation_reasons:
                mode = data_mode_for_quote(quote)
                leaf_provider = leaf_provider_for_quote(quote)
                quality = assess_quote_quality(quote, provider=candidate.provider, mode=mode, fetched_at=_now())
                selected_status = ProviderStatus(
                    provider=status.provider,
                    service=MARKET_DATA_SERVICE,
                    status=status.status,
                    message=status.message,
                    configured=status.configured,
                    available=True,
                    stale=status.stale,
                    source_timestamp=status.source_timestamp or quote.market_timestamp,
                    checked_at=status.checked_at,
                )
                attempts.append(attempt_from_status(selected_status, selected=True, duration_ms=_duration_ms(started_at)))
                self.health.record(provider=candidate.provider, service=MARKET_DATA_SERVICE, configured=True, status=selected_status.status, fallback_used=bool(attempts[:-1]), latency_ms=_duration_ms(started_at))
                if self.cache is not None:
                    self.cache.set(
                        cache_key,
                        CacheEntry(
                            data=quote,
                            provider=candidate.provider,
                            leaf_provider=leaf_provider,
                            mode=mode,
                            source_timestamp=_quote_timestamp(quote),
                            fetched_at=_now(),
                            quality=quality,
                        ),
                    )
                return ProviderResult(
                    data=quote,
                    status=selected_status,
                    provider=candidate.provider,
                    service=MARKET_DATA_SERVICE,
                    source_timestamp=_quote_timestamp(quote),
                    fetched_at=_now(),
                    fallback_used=len([attempt for attempt in attempts if not attempt.selected]) > 0,
                    attempts=attempts,
                    message=selected_status.message,
                    leaf_provider=leaf_provider,
                    data_mode=mode,
                    freshness=quality.freshness,
                    quality=quality,
                )

            category = ProviderFailureCategory.UNCONFIGURED if status.status == DataSourceState.UNCONFIGURED else ProviderFailureCategory.NO_DATA
            message = "; ".join(validation_reasons) if validation_reasons else status.message
            failed_status = status_from_category(candidate.provider, MARKET_DATA_SERVICE, category, message)
            attempts.append(attempt_from_status(failed_status, category=category, duration_ms=_duration_ms(started_at)))
            self.health.record(provider=candidate.provider, service=MARKET_DATA_SERVICE, configured=True, status=failed_status.status, failure_category=category, latency_ms=_duration_ms(started_at))

        stale = self.cache.get_stale(cache_key) if self.cache is not None else None
        if stale is not None:
            quote = stale.data
            mode = DataMode.STALE_CACHE
            quality = assess_quote_quality(quote, provider=stale.provider, mode=mode, fetched_at=_now())  # type: ignore[arg-type]
            status = ProviderStatus.stale_status(stale.provider, MARKET_DATA_SERVICE, "Live quote failed; stale cached quote returned.", source_timestamp=stale.source_timestamp)
            attempts.append(attempt_from_status(status, category=ProviderFailureCategory.STALE_DATA, selected=True))
            self.health.record(provider=stale.provider, service=MARKET_DATA_SERVICE, configured=True, status=status.status, failure_category=ProviderFailureCategory.STALE_DATA, fallback_used=True)
            return ProviderResult(
                data=quote,  # type: ignore[arg-type]
                status=status,
                provider=stale.provider,
                service=MARKET_DATA_SERVICE,
                source_timestamp=stale.source_timestamp,
                fetched_at=_now(),
                from_cache=True,
                fallback_used=True,
                attempts=attempts,
                message=status.message,
                leaf_provider=stale.leaf_provider,
                data_mode=mode,
                freshness=quality.freshness,
                quality=quality,
            )

        final_quote = UnavailableMarketProvider().fetch_quote_snapshot(symbol)
        category = ProviderFailureCategory.UNSUPPORTED_SYMBOL if unsupported_seen and not attempts else ProviderFailureCategory.NO_DATA
        status = status_from_category("unavailable", MARKET_DATA_SERVICE, category, "No usable market quote provider produced data.")
        final_quote.provider_status = status
        final_quote.quality_status = "unavailable"
        final_quote.note = status.message
        attempts.append(attempt_from_status(status, category=category, selected=True))
        self.health.record(provider="unavailable", service=MARKET_DATA_SERVICE, configured=False, status=status.status, failure_category=category, fallback_used=bool(attempts[:-1]))
        return ProviderResult(
            data=final_quote,
            status=status,
            provider="unavailable",
            service=MARKET_DATA_SERVICE,
            fetched_at=_now(),
            fallback_used=bool(attempts[:-1]),
            attempts=attempts,
            message=status.message,
            leaf_provider="unavailable",
            data_mode=DataMode.UNKNOWN,
        )

    def fetch_price_bars(
        self,
        symbol: SymbolRecord,
        *,
        start: datetime,
        end: datetime,
        interval: str,
    ) -> ProviderResult[pd.DataFrame]:
        attempts: list[ProviderAttempt] = []
        unsupported_seen = False
        cache_key = ("bars", symbol.internal_id, start.isoformat(), end.isoformat(), interval)
        cached = self.cache.get(cache_key, settings.price_history_cache_ttl_seconds) if self.cache is not None else None
        if cached is not None:
            frame = cached.data
            quality = assess_bars_quality(frame, provider=cached.provider, mode=DataMode.CACHED, source_timestamp=cached.source_timestamp, fetched_at=_now())  # type: ignore[arg-type]
            status = ProviderStatus.degraded(cached.provider, HISTORICAL_DATA_SERVICE, "Historical bars returned from in-memory cache.", source_timestamp=cached.source_timestamp)
            return ProviderResult(
                data=frame,  # type: ignore[arg-type]
                status=status,
                provider=cached.provider,
                service=HISTORICAL_DATA_SERVICE,
                source_timestamp=cached.source_timestamp,
                fetched_at=_now(),
                from_cache=True,
                attempts=[attempt_from_status(status, selected=True)],
                message=status.message,
                leaf_provider=cached.leaf_provider,
                data_mode=DataMode.CACHED,
                freshness=quality.freshness,
                quality=quality,
            )

        for candidate in self.candidates or []:
            if not candidate.supports_exchange(symbol.exchange):
                unsupported_seen = True
                continue
            if not candidate.configured():
                status = ProviderStatus.unconfigured(candidate.provider, HISTORICAL_DATA_SERVICE, candidate.unconfigured_message)
                attempts.append(attempt_from_status(status, category=ProviderFailureCategory.UNCONFIGURED))
                self.health.record(provider=candidate.provider, service=HISTORICAL_DATA_SERVICE, configured=False, status=status.status, failure_category=ProviderFailureCategory.UNCONFIGURED)
                continue

            provider = candidate.factory()
            started_at = perf_counter()
            try:
                frame = call_with_retries(
                    lambda: provider.fetch_price_bars(symbol, start=start, end=end, interval=interval),  # type: ignore[attr-defined]
                    sleep=self.sleep or (lambda _: None),
                )
            except Exception as exc:
                category = classify_exception(exc)
                latency = _duration_ms(started_at)
                status = status_from_category(candidate.provider, HISTORICAL_DATA_SERVICE, category, f"Historical bars request failed: {safe_log_message(exc)}")
                attempts.append(attempt_from_status(status, category=category, duration_ms=latency))
                self.health.record(provider=candidate.provider, service=HISTORICAL_DATA_SERVICE, configured=True, status=status.status, failure_category=category, latency_ms=latency, status_code=_status_code(exc))
                continue

            validation_reasons = validate_bars_frame(frame)
            if frame is not None and not frame.empty and not validation_reasons:
                latest_timestamp = pd.to_datetime(frame.index, errors="coerce").max()
                source_timestamp = latest_timestamp.to_pydatetime() if pd.notna(latest_timestamp) else None
                quality = assess_bars_quality(frame, provider=candidate.provider, mode=DataMode.HISTORICAL, source_timestamp=source_timestamp, fetched_at=_now())
                status = ProviderStatus.available_status(
                    candidate.provider,
                    HISTORICAL_DATA_SERVICE,
                    "Historical bars available from provider.",
                    source_timestamp=source_timestamp,
                )
                attempts.append(attempt_from_status(status, selected=True, duration_ms=_duration_ms(started_at)))
                self.health.record(provider=candidate.provider, service=HISTORICAL_DATA_SERVICE, configured=True, status=status.status, fallback_used=bool(attempts[:-1]), latency_ms=_duration_ms(started_at))
                if self.cache is not None:
                    self.cache.set(
                        cache_key,
                        CacheEntry(
                            data=frame,
                            provider=candidate.provider,
                            leaf_provider=candidate.provider,
                            mode=DataMode.HISTORICAL,
                            source_timestamp=source_timestamp,
                            fetched_at=_now(),
                            quality=quality,
                        ),
                    )
                return ProviderResult(
                    data=frame,
                    status=status,
                    provider=candidate.provider,
                    service=HISTORICAL_DATA_SERVICE,
                    source_timestamp=source_timestamp,
                    fetched_at=_now(),
                    fallback_used=len([attempt for attempt in attempts if not attempt.selected]) > 0,
                    attempts=attempts,
                    message=status.message,
                    leaf_provider=candidate.provider,
                    data_mode=DataMode.HISTORICAL,
                    freshness=quality.freshness,
                    quality=quality,
                )

            status = status_from_category(candidate.provider, HISTORICAL_DATA_SERVICE, ProviderFailureCategory.NO_DATA, "; ".join(validation_reasons) if validation_reasons else "Provider returned no historical bars.")
            attempts.append(attempt_from_status(status, category=ProviderFailureCategory.NO_DATA, duration_ms=_duration_ms(started_at)))
            self.health.record(provider=candidate.provider, service=HISTORICAL_DATA_SERVICE, configured=True, status=status.status, failure_category=ProviderFailureCategory.NO_DATA, latency_ms=_duration_ms(started_at))

        stale = self.cache.get_stale(cache_key) if self.cache is not None else None
        if stale is not None:
            frame = stale.data
            quality = assess_bars_quality(frame, provider=stale.provider, mode=DataMode.STALE_CACHE, source_timestamp=stale.source_timestamp, fetched_at=_now())  # type: ignore[arg-type]
            status = ProviderStatus.stale_status(stale.provider, HISTORICAL_DATA_SERVICE, "Live bars failed; stale cached bars returned.", source_timestamp=stale.source_timestamp)
            attempts.append(attempt_from_status(status, category=ProviderFailureCategory.STALE_DATA, selected=True))
            return ProviderResult(
                data=frame,  # type: ignore[arg-type]
                status=status,
                provider=stale.provider,
                service=HISTORICAL_DATA_SERVICE,
                source_timestamp=stale.source_timestamp,
                fetched_at=_now(),
                from_cache=True,
                fallback_used=True,
                attempts=attempts,
                message=status.message,
                leaf_provider=stale.leaf_provider,
                data_mode=DataMode.STALE_CACHE,
                freshness=quality.freshness,
                quality=quality,
            )

        category = ProviderFailureCategory.UNSUPPORTED_SYMBOL if unsupported_seen and not attempts else ProviderFailureCategory.NO_DATA
        status = status_from_category("unavailable", HISTORICAL_DATA_SERVICE, category, "No historical bar provider produced data.")
        attempts.append(attempt_from_status(status, category=category, selected=True))
        self.health.record(provider="unavailable", service=HISTORICAL_DATA_SERVICE, configured=False, status=status.status, failure_category=category, fallback_used=bool(attempts[:-1]))
        return ProviderResult(
            data=_empty_bars(),
            status=status,
            provider="unavailable",
            service=HISTORICAL_DATA_SERVICE,
            fetched_at=_now(),
            fallback_used=bool(attempts[:-1]),
            attempts=attempts,
            message=status.message,
            leaf_provider="unavailable",
            data_mode=DataMode.UNKNOWN,
        )


@dataclass(slots=True)
class NewsProviderRouter:
    candidates: list[ProviderCandidate] | None = None
    cache: ProviderTTLCache | None = None
    health: ProviderHealthRegistry | None = None
    clock: Callable[[], datetime] | None = None
    sleep: Callable[[float], None] | None = None

    def __post_init__(self) -> None:
        if self.candidates is None:
            self.candidates = default_news_candidates()
        if self.cache is None:
            self.cache = ProviderTTLCache(clock=self.clock, name="news_provider")
        if self.health is None:
            self.health = ProviderHealthRegistry(clock=self.clock)

    def fetch_news(self, symbol: SymbolRecord, *, limit: int | None = None) -> ProviderResult[list[NormalizedNewsArticle]]:
        requested_limit = normalize_news_limit(limit, default=settings.default_news_limit)
        attempts: list[ProviderAttempt] = []
        unsupported_seen = False
        cache_key = ("news", symbol.internal_id, requested_limit)
        cached = self.cache.get(cache_key, settings.news_cache_ttl_seconds) if self.cache is not None else None
        if cached is not None:
            articles = cached.data
            quality = assess_news_quality(articles, provider=cached.provider, mode=DataMode.CACHED, source_timestamp=cached.source_timestamp, fallback_used=False, fetched_at=_now())  # type: ignore[arg-type]
            status = ProviderStatus.degraded(cached.provider, NEWS_SERVICE, "News returned from in-memory cache.", source_timestamp=cached.source_timestamp)
            return ProviderResult(
                data=articles,  # type: ignore[arg-type]
                status=status,
                provider=cached.provider,
                service=NEWS_SERVICE,
                source_timestamp=cached.source_timestamp,
                fetched_at=_now(),
                from_cache=True,
                attempts=[attempt_from_status(status, selected=True)],
                message=status.message,
                leaf_provider=cached.leaf_provider,
                data_mode=DataMode.CACHED,
                freshness=quality.freshness,
                quality=quality,
            )

        for candidate in self.candidates or []:
            if not candidate.supports_exchange(symbol.exchange):
                unsupported_seen = True
                continue
            if not candidate.configured():
                status = ProviderStatus.unconfigured(candidate.provider, NEWS_SERVICE, candidate.unconfigured_message)
                attempts.append(attempt_from_status(status, category=ProviderFailureCategory.UNCONFIGURED))
                self.health.record(provider=candidate.provider, service=NEWS_SERVICE, configured=False, status=status.status, failure_category=ProviderFailureCategory.UNCONFIGURED)
                continue

            provider = candidate.factory()
            started_at = perf_counter()
            try:
                articles = call_with_retries(
                    lambda: provider.fetch_news(symbol, limit=requested_limit),  # type: ignore[attr-defined]
                    sleep=self.sleep or (lambda _: None),
                )
            except Exception as exc:
                category = classify_exception(exc)
                retry_after = retry_after_seconds(exc)
                latency = _duration_ms(started_at)
                extra = f" Retry-After={retry_after}s." if retry_after is not None else ""
                status = status_from_category(candidate.provider, NEWS_SERVICE, category, f"News request failed: {safe_log_message(exc)}.{extra}")
                attempts.append(attempt_from_status(status, category=category, duration_ms=latency))
                self.health.record(provider=candidate.provider, service=NEWS_SERVICE, configured=True, status=status.status, failure_category=category, latency_ms=latency, status_code=_status_code(exc))
                continue

            valid_articles, validation_reasons = validate_news_articles(articles)
            if valid_articles:
                source_timestamp = max(article.published_at for article in articles)
                leaf_provider = getattr(provider, "leaf_provider", None) or candidate.provider
                mode = _coerce_data_mode(
                    getattr(provider, "data_mode", None),
                    DataMode.SCRAPED if candidate.provider == "fallback_web" else DataMode.LIVE,
                )
                quality = assess_news_quality(valid_articles, provider=candidate.provider, mode=mode, source_timestamp=source_timestamp, fallback_used=bool(attempts), fetched_at=_now())
                status = ProviderStatus.available_status(
                    candidate.provider,
                    NEWS_SERVICE,
                    "News articles available from provider.",
                    source_timestamp=source_timestamp,
                )
                attempts.append(attempt_from_status(status, selected=True, duration_ms=_duration_ms(started_at)))
                self.health.record(provider=candidate.provider, service=NEWS_SERVICE, configured=True, status=status.status, fallback_used=bool(attempts[:-1]), latency_ms=_duration_ms(started_at))
                if self.cache is not None:
                    self.cache.set(
                        cache_key,
                        CacheEntry(
                            data=valid_articles,
                            provider=candidate.provider,
                            leaf_provider=leaf_provider,
                            mode=mode,
                            source_timestamp=source_timestamp,
                            fetched_at=_now(),
                            quality=quality,
                        ),
                    )
                return ProviderResult(
                    data=valid_articles,
                    status=status,
                    provider=candidate.provider,
                    service=NEWS_SERVICE,
                    source_timestamp=source_timestamp,
                    fetched_at=_now(),
                    fallback_used=len([attempt for attempt in attempts if not attempt.selected]) > 0,
                    attempts=attempts,
                    message=status.message,
                    leaf_provider=leaf_provider,
                    data_mode=mode,
                    freshness=quality.freshness,
                    quality=quality,
                )

            status = status_from_category(candidate.provider, NEWS_SERVICE, ProviderFailureCategory.NO_DATA, "; ".join(validation_reasons) if validation_reasons else "Provider returned no usable news articles.")
            attempts.append(attempt_from_status(status, category=ProviderFailureCategory.NO_DATA, duration_ms=_duration_ms(started_at)))
            self.health.record(provider=candidate.provider, service=NEWS_SERVICE, configured=True, status=status.status, failure_category=ProviderFailureCategory.NO_DATA, latency_ms=_duration_ms(started_at))

        stale = self.cache.get_stale(cache_key) if self.cache is not None else None
        if stale is not None:
            articles = stale.data
            quality = assess_news_quality(articles, provider=stale.provider, mode=DataMode.STALE_CACHE, source_timestamp=stale.source_timestamp, fallback_used=True, fetched_at=_now())  # type: ignore[arg-type]
            status = ProviderStatus.stale_status(stale.provider, NEWS_SERVICE, "Live news failed; stale cached news returned.", source_timestamp=stale.source_timestamp)
            attempts.append(attempt_from_status(status, category=ProviderFailureCategory.STALE_DATA, selected=True))
            self.health.record(provider=stale.provider, service=NEWS_SERVICE, configured=True, status=status.status, failure_category=ProviderFailureCategory.STALE_DATA, fallback_used=True)
            return ProviderResult(
                data=articles,  # type: ignore[arg-type]
                status=status,
                provider=stale.provider,
                service=NEWS_SERVICE,
                source_timestamp=stale.source_timestamp,
                fetched_at=_now(),
                from_cache=True,
                fallback_used=True,
                attempts=attempts,
                message=status.message,
                leaf_provider=stale.leaf_provider,
                data_mode=DataMode.STALE_CACHE,
                freshness=quality.freshness,
                quality=quality,
            )

        category = ProviderFailureCategory.UNSUPPORTED_SYMBOL if unsupported_seen and not attempts else ProviderFailureCategory.NO_DATA
        status = status_from_category("unavailable", NEWS_SERVICE, category, "No news provider produced usable articles.")
        attempts.append(attempt_from_status(status, category=category, selected=True))
        self.health.record(provider="unavailable", service=NEWS_SERVICE, configured=False, status=status.status, failure_category=category, fallback_used=bool(attempts[:-1]))
        return ProviderResult(
            data=[],
            status=status,
            provider="unavailable",
            service=NEWS_SERVICE,
            fetched_at=_now(),
            fallback_used=bool(attempts[:-1]),
            attempts=attempts,
            message=status.message,
            leaf_provider="unavailable",
            data_mode=DataMode.UNKNOWN,
        )


def default_market_candidates() -> list[ProviderCandidate]:
    return [
        ProviderCandidate(
            provider="alpaca",
            service=MARKET_DATA_SERVICE,
            supports_exchange=lambda exchange: exchange == "US",
            configured=lambda: bool(settings.alpaca_api_key and settings.alpaca_api_secret),
            factory=lambda: AlpacaMarketDataProvider(),
            unconfigured_message="ALPACA_API_KEY or ALPACA_API_SECRET is not configured.",
        ),
        ProviderCandidate(
            provider="polygon",
            service=MARKET_DATA_SERVICE,
            supports_exchange=lambda exchange: exchange == "US",
            configured=lambda: bool(settings.polygon_api_key),
            factory=lambda: PolygonMarketDataProvider(),
            unconfigured_message="POLYGON_API_KEY is not configured.",
        ),
        ProviderCandidate(
            provider="kite",
            service=MARKET_DATA_SERVICE,
            supports_exchange=lambda exchange: exchange in {"NSE", "BSE"},
            configured=lambda: bool(settings.kite_api_key and settings.kite_access_token),
            factory=lambda: KiteMarketDataProvider(),
            unconfigured_message="KITE_API_KEY or KITE_ACCESS_TOKEN is not configured.",
        ),
        ProviderCandidate(
            provider="yahoo_chart",
            service=MARKET_DATA_SERVICE,
            supports_exchange=lambda exchange: exchange in {"NSE", "BSE"},
            configured=lambda: True,
            factory=lambda: YahooHistoricalMarketDataProvider(),
            unconfigured_message="Yahoo Chart Indian market fallback is unavailable.",
        ),
    ]


def default_news_candidates() -> list[ProviderCandidate]:
    return [
        ProviderCandidate(
            provider="alpaca",
            service=NEWS_SERVICE,
            supports_exchange=lambda exchange: exchange == "US",
            configured=lambda: bool(settings.alpaca_api_key and settings.alpaca_api_secret),
            factory=lambda: AlpacaNewsProvider(),
            unconfigured_message="ALPACA_API_KEY or ALPACA_API_SECRET is not configured.",
        ),
        ProviderCandidate(
            provider="polygon",
            service=NEWS_SERVICE,
            supports_exchange=lambda exchange: exchange == "US",
            configured=lambda: bool(settings.polygon_api_key),
            factory=lambda: PolygonNewsProvider(),
            unconfigured_message="POLYGON_API_KEY is not configured.",
        ),
        ProviderCandidate(
            provider="marketaux",
            service=NEWS_SERVICE,
            supports_exchange=lambda exchange: exchange in {"US", "NSE", "BSE"},
            configured=lambda: bool(settings.marketaux_api_token),
            factory=lambda: MarketauxNewsProvider(),
            unconfigured_message="MARKETAUX_API_TOKEN is not configured.",
        ),
        ProviderCandidate(
            provider="fallback_web",
            service=NEWS_SERVICE,
            supports_exchange=lambda exchange: exchange in {"US", "NSE", "BSE"},
            configured=lambda: True,
            factory=lambda: CuratedWebNewsProvider(),
            unconfigured_message="Fallback web news provider is always available.",
        ),
    ]
