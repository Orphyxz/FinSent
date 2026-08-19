from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
import math
import time
from threading import RLock
from typing import Generic, TypeVar

import pandas as pd
import requests

from finsent.app.config.settings import settings
from finsent.app.services.market_providers import QuoteSnapshot, is_usable_quote_snapshot
from finsent.app.services.news_providers import NormalizedNewsArticle
from finsent.app.services.provider_contracts import ProviderFailureCategory, classify_exception
from finsent.app.services.provider_status import DataSourceState, ProviderStatus
from finsent.app.services.runtime_diagnostics import CacheStats, runtime_diagnostics


T = TypeVar("T")


class DataMode(str, Enum):
    LIVE = "LIVE"
    DELAYED = "DELAYED"
    CACHED = "CACHED"
    STALE_CACHE = "STALE_CACHE"
    HISTORICAL = "HISTORICAL"
    PREVIOUS_CLOSE = "PREVIOUS_CLOSE"
    SCRAPED = "SCRAPED"
    SEARCH_DERIVED = "SEARCH_DERIVED"
    LOCAL_DATASET = "LOCAL_DATASET"
    UNKNOWN = "UNKNOWN"


class FreshnessLabel(str, Enum):
    FRESH = "FRESH"
    AGING = "AGING"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class DataQualityLabel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class DataQualityAssessment:
    score: float
    label: DataQualityLabel
    reasons: list[str]
    freshness: FreshnessLabel
    provider: str
    mode: DataMode
    evaluated_at: datetime


@dataclass(slots=True)
class CacheEntry(Generic[T]):
    data: T
    provider: str
    leaf_provider: str
    mode: DataMode
    source_timestamp: datetime | None
    fetched_at: datetime
    quality: DataQualityAssessment | None = None


class ProviderTTLCache:
    def __init__(self, clock: Callable[[], datetime] | None = None, *, name: str = "provider_ttl_cache") -> None:
        self._clock = clock or utc_now
        self.name = name
        self._lock = RLock()
        self._entries: dict[tuple[object, ...], CacheEntry[object]] = {}
        self._hits = 0
        self._misses = 0
        self._stale_hits = 0
        self._expired = 0
        self._evictions = 0

    def get(self, key: tuple[object, ...], ttl_seconds: int) -> CacheEntry[object] | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                self._misses += 1
                self._publish_stats()
                return None
            age = (self._clock() - entry.fetched_at).total_seconds()
            if age <= ttl_seconds:
                self._hits += 1
                self._publish_stats()
                return entry
            self._expired += 1
            self._misses += 1
            self._publish_stats()
            return None

    def get_stale(self, key: tuple[object, ...]) -> CacheEntry[object] | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None:
                self._stale_hits += 1
            self._publish_stats()
            return entry

    def set(self, key: tuple[object, ...], entry: CacheEntry[object]) -> None:
        with self._lock:
            self._entries[key] = entry
            self._publish_stats()

    def clear(self) -> None:
        with self._lock:
            self._evictions += len(self._entries)
            self._entries.clear()
            self._publish_stats()

    def stats(self) -> CacheStats:
        with self._lock:
            return CacheStats(
                name=self.name,
                hits=self._hits,
                misses=self._misses,
                stale_hits=self._stale_hits,
                expired=self._expired,
                evictions=self._evictions,
                entries=len(self._entries),
            )

    def _publish_stats(self) -> None:
        runtime_diagnostics.record_cache_stats(
            CacheStats(
                name=self.name,
                hits=self._hits,
                misses=self._misses,
                stale_hits=self._stale_hits,
                expired=self._expired,
                evictions=self._evictions,
                entries=len(self._entries),
            )
        )


@dataclass(slots=True)
class ProviderHealthRecord:
    provider: str
    service: str
    configured: bool
    last_status: DataSourceState
    last_successful_fetch: datetime | None = None
    last_failure: datetime | None = None
    last_failure_category: ProviderFailureCategory | None = None
    last_checked: datetime | None = None
    last_latency_ms: int | None = None
    success_count: int = 0
    failure_count: int = 0
    consecutive_failures: int = 0
    rate_limited: bool = False
    last_status_code: int | None = None
    circuit_state: str | None = None
    recent_fallback_used: bool = False


class ProviderHealthRegistry:
    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or utc_now
        self._records: dict[tuple[str, str], ProviderHealthRecord] = {}

    def record(
        self,
        *,
        provider: str,
        service: str,
        configured: bool,
        status: DataSourceState,
        failure_category: ProviderFailureCategory | None = None,
        fallback_used: bool = False,
        latency_ms: int | None = None,
        status_code: int | None = None,
    ) -> None:
        key = (provider, service)
        now = self._clock()
        previous = self._records.get(key)
        last_success = previous.last_successful_fetch if previous is not None else None
        success_count = previous.success_count if previous is not None else 0
        failure_count = previous.failure_count if previous is not None else 0
        consecutive_failures = previous.consecutive_failures if previous is not None else 0
        last_failure = previous.last_failure if previous is not None else None
        if status == DataSourceState.AVAILABLE:
            last_success = now
            success_count += 1
            consecutive_failures = 0
        elif status != DataSourceState.UNCONFIGURED:
            failure_count += 1
            consecutive_failures += 1
            last_failure = now
        self._records[key] = ProviderHealthRecord(
            provider=provider,
            service=service,
            configured=configured,
            last_status=status,
            last_successful_fetch=last_success,
            last_failure=last_failure,
            last_failure_category=failure_category,
            last_checked=now,
            last_latency_ms=latency_ms,
            success_count=success_count,
            failure_count=failure_count,
            consecutive_failures=consecutive_failures,
            rate_limited=failure_category == ProviderFailureCategory.RATE_LIMIT,
            last_status_code=status_code,
            circuit_state=None,
            recent_fallback_used=fallback_used,
        )
        runtime_diagnostics.record_provider_health(self.snapshot())

    def snapshot(self) -> list[ProviderHealthRecord]:
        return sorted(self._records.values(), key=lambda row: (row.provider, row.service))


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def finite_number(value: object) -> bool:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    return math.isfinite(number)


def validate_quote_snapshot(quote: QuoteSnapshot | None) -> list[str]:
    reasons: list[str] = []
    if quote is None:
        return ["quote is missing"]
    if not is_usable_quote_snapshot(quote):
        reasons.append("quote is not usable")
    if quote.current_price is None or not finite_number(quote.current_price) or float(quote.current_price) <= 0:
        reasons.append("price must be finite and greater than zero")
    if quote.market_timestamp is None:
        reasons.append("timestamp is missing")
    if quote.bid is not None and not finite_number(quote.bid):
        reasons.append("bid is malformed")
    if quote.ask is not None and not finite_number(quote.ask):
        reasons.append("ask is malformed")
    if quote.bid is not None and quote.ask is not None and finite_number(quote.bid) and finite_number(quote.ask):
        if float(quote.bid) > float(quote.ask):
            reasons.append("bid cannot exceed ask")
    if quote.volume is not None and (not finite_number(quote.volume) or float(quote.volume) < 0):
        reasons.append("volume cannot be negative or malformed")
    return reasons


def validate_bars_frame(frame: pd.DataFrame | None) -> list[str]:
    if frame is None or frame.empty:
        return ["historical bars are empty"]
    reasons: list[str] = []
    required = ["Open", "High", "Low", "Close", "Volume"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        return [f"missing columns: {', '.join(missing)}"]
    timestamps = pd.to_datetime(frame.index, errors="coerce")
    if timestamps.isna().any():
        reasons.append("bar timestamp is invalid")
    if timestamps.duplicated().any():
        reasons.append("duplicate bar timestamps")
    if not timestamps.is_monotonic_increasing:
        reasons.append("bars are not chronologically ordered")
    numeric = frame[required].apply(pd.to_numeric, errors="coerce")
    if numeric[["Open", "High", "Low", "Close"]].isna().any().any():
        reasons.append("OHLC contains malformed values")
    if (numeric[["Open", "High", "Low", "Close"]] <= 0).any().any():
        reasons.append("OHLC values must be greater than zero")
    if (numeric["Volume"] < 0).any():
        reasons.append("volume cannot be negative")
    if (numeric["High"] < numeric["Low"]).any():
        reasons.append("high cannot be below low")
    if (numeric["High"] < numeric[["Open", "Close"]].max(axis=1)).any():
        reasons.append("high must be at least open and close")
    if (numeric["Low"] > numeric[["Open", "Close"]].min(axis=1)).any():
        reasons.append("low must be at most open and close")
    return reasons


def validate_news_articles(articles: list[NormalizedNewsArticle] | None) -> tuple[list[NormalizedNewsArticle], list[str]]:
    if not articles:
        return [], ["news articles are empty"]
    valid: list[NormalizedNewsArticle] = []
    reasons: list[str] = []
    for article in articles:
        if not article.title or not article.title.strip():
            reasons.append("article title is empty")
            continue
        if not article.source or not article.source.strip():
            reasons.append("article source is empty")
            continue
        if article.published_at is None:
            reasons.append("article publication timestamp is missing")
            continue
        if article.url and not article.url.lower().startswith(("http://", "https://")):
            reasons.append("article URL is malformed")
            continue
        valid.append(article)
    if not valid and not reasons:
        reasons.append("no valid articles")
    return valid, reasons


def data_mode_for_quote(quote: QuoteSnapshot | None) -> DataMode:
    if quote is None:
        return DataMode.UNKNOWN
    note = (quote.note or "").lower()
    quality = (quote.quality_status or "").lower()
    if "previous-close" in note or "previous close" in note:
        return DataMode.PREVIOUS_CLOSE
    if quality == "live":
        return DataMode.LIVE
    if quality == "delayed":
        return DataMode.DELAYED
    if quality == "stale":
        return DataMode.PREVIOUS_CLOSE
    return DataMode.UNKNOWN


def leaf_provider_for_quote(quote: QuoteSnapshot | None) -> str:
    if quote is None:
        return "unavailable"
    note = (quote.note or "").lower()
    provider = quote.provider or "unknown"
    if "last trade" in note:
        return f"{provider}/last_trade"
    if "previous-close" in note or "previous close" in note:
        return f"{provider}/previous_close"
    if "snapshot" in note:
        return f"{provider}/snapshot"
    return provider


def assess_freshness(
    source_timestamp: datetime | None,
    fetched_at: datetime | None,
    mode: DataMode,
) -> FreshnessLabel:
    if source_timestamp is None or fetched_at is None:
        return FreshnessLabel.UNKNOWN
    age = max((fetched_at - source_timestamp).total_seconds(), 0.0)
    if mode == DataMode.PREVIOUS_CLOSE:
        return FreshnessLabel.STALE if age > 36 * 3600 else FreshnessLabel.AGING
    if mode in {DataMode.LIVE, DataMode.DELAYED, DataMode.CACHED}:
        if age <= settings.quote_fresh_seconds:
            return FreshnessLabel.FRESH
        if age <= settings.quote_aging_seconds:
            return FreshnessLabel.AGING
        return FreshnessLabel.STALE
    if mode == DataMode.STALE_CACHE:
        return FreshnessLabel.STALE
    if mode in {DataMode.SCRAPED, DataMode.SEARCH_DERIVED}:
        if age <= settings.news_fresh_minutes * 60:
            return FreshnessLabel.FRESH
        if age <= settings.news_aging_minutes * 60:
            return FreshnessLabel.AGING
        return FreshnessLabel.STALE
    if mode in {DataMode.HISTORICAL, DataMode.LOCAL_DATASET}:
        return FreshnessLabel.AGING
    return FreshnessLabel.UNKNOWN


def quality_label(score: float) -> DataQualityLabel:
    if score <= 0:
        return DataQualityLabel.UNAVAILABLE
    if score >= 0.8:
        return DataQualityLabel.HIGH
    if score >= 0.5:
        return DataQualityLabel.MEDIUM
    return DataQualityLabel.LOW


def assess_quote_quality(quote: QuoteSnapshot | None, *, provider: str, mode: DataMode, fetched_at: datetime | None = None) -> DataQualityAssessment:
    fetched = fetched_at or utc_now()
    freshness = assess_freshness(quote.market_timestamp if quote else None, fetched, mode)
    reasons = validate_quote_snapshot(quote)
    score = 1.0 if not reasons else 0.0
    if mode == DataMode.PREVIOUS_CLOSE:
        score -= 0.35
        reasons.append("previous close is not live market data")
    if freshness == FreshnessLabel.AGING:
        score -= 0.15
        reasons.append("quote is aging")
    elif freshness == FreshnessLabel.STALE:
        score -= 0.35
        reasons.append("quote is stale")
    elif freshness == FreshnessLabel.UNKNOWN:
        score -= 0.2
        reasons.append("quote freshness is unknown")
    if quote is not None and quote.spread_percentage is None:
        score -= 0.1
        reasons.append("spread is unavailable")
    return DataQualityAssessment(max(min(score, 1.0), 0.0), quality_label(max(min(score, 1.0), 0.0)), reasons, freshness, provider, mode, fetched)


def assess_bars_quality(frame: pd.DataFrame | None, *, provider: str, mode: DataMode, source_timestamp: datetime | None, fetched_at: datetime | None = None) -> DataQualityAssessment:
    fetched = fetched_at or utc_now()
    freshness = assess_freshness(source_timestamp, fetched, mode)
    reasons = validate_bars_frame(frame)
    score = 1.0 if not reasons else 0.0
    if freshness == FreshnessLabel.UNKNOWN:
        score -= 0.2
        reasons.append("bar freshness is unknown")
    if frame is not None and not frame.empty and len(frame) < 2:
        score -= 0.15
        reasons.append("bar history is sparse")
    return DataQualityAssessment(max(min(score, 1.0), 0.0), quality_label(max(min(score, 1.0), 0.0)), reasons, freshness, provider, mode, fetched)


def assess_news_quality(articles: list[NormalizedNewsArticle] | None, *, provider: str, mode: DataMode, source_timestamp: datetime | None, fallback_used: bool, fetched_at: datetime | None = None) -> DataQualityAssessment:
    fetched = fetched_at or utc_now()
    valid_articles, validation_reasons = validate_news_articles(articles)
    freshness = assess_freshness(source_timestamp, fetched, mode)
    reasons = list(validation_reasons)
    score = 1.0 if valid_articles else 0.0
    if fallback_used:
        score -= 0.15
        reasons.append("fallback provider was used")
    if mode == DataMode.SCRAPED:
        score -= 0.25
        reasons.append("HTML scraping is structurally fragile")
    elif mode == DataMode.SEARCH_DERIVED:
        score -= 0.15
        reasons.append("search-derived news has weaker provider metadata")
    if freshness == FreshnessLabel.AGING:
        score -= 0.1
        reasons.append("news is aging")
    elif freshness == FreshnessLabel.STALE:
        score -= 0.3
        reasons.append("news is stale")
    elif freshness == FreshnessLabel.UNKNOWN:
        score -= 0.2
        reasons.append("news freshness is unknown")
    if valid_articles and len(valid_articles) < 3:
        score -= 0.1
        reasons.append("article count is low")
    return DataQualityAssessment(max(min(score, 1.0), 0.0), quality_label(max(min(score, 1.0), 0.0)), reasons, freshness, provider, mode, fetched)


def should_retry(category: ProviderFailureCategory) -> bool:
    return category in {ProviderFailureCategory.TIMEOUT, ProviderFailureCategory.NETWORK}


def call_with_retries(
    operation: Callable[[], T],
    *,
    retry_count: int | None = None,
    backoff_seconds: float | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    retries = settings.provider_retry_count if retry_count is None else retry_count
    backoff = settings.provider_retry_backoff_seconds if backoff_seconds is None else backoff_seconds
    attempt = 0
    while True:
        try:
            return operation()
        except Exception as exc:
            category = classify_exception(exc)
            if attempt >= retries or not should_retry(category):
                raise
            sleep(backoff * (2**attempt))
            attempt += 1


def retry_after_seconds(exc: Exception) -> int | None:
    response = getattr(exc, "response", None)
    if response is None:
        return None
    raw = response.headers.get("Retry-After") if hasattr(response, "headers") else None
    if raw is None:
        return None
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        return None
    return max(parsed, 0)
