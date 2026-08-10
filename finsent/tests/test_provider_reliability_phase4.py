from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import pytest
import requests

from finsent.app.config.settings import settings
from finsent.app.services.market_providers import QuoteSnapshot, is_usable_quote_snapshot
from finsent.app.services.news_providers import NormalizedNewsArticle
from finsent.app.services.provider_contracts import ProviderCandidate, ProviderFailureCategory, classify_exception
from finsent.app.services.provider_reliability import (
    CacheEntry,
    DataMode,
    DataQualityLabel,
    FreshnessLabel,
    ProviderHealthRegistry,
    ProviderTTLCache,
    assess_freshness,
    assess_news_quality,
    assess_quote_quality,
    call_with_retries,
    leaf_provider_for_quote,
    retry_after_seconds,
    validate_bars_frame,
    validate_news_articles,
    validate_quote_snapshot,
)
from finsent.app.services.provider_routers import MarketDataRouter, NewsProviderRouter
from finsent.app.services.provider_status import DataSourceState, ProviderStatus
from finsent.app.services.symbol_registry import registry


NOW = datetime(2026, 8, 9, 10, 0, 0)


def _quote(provider: str = "polygon", *, note: str = "Polygon single-ticker snapshot", **overrides) -> QuoteSnapshot:
    values = {
        "symbol": "AAPL",
        "exchange": "US",
        "provider_symbol": "AAPL",
        "current_price": 200.0,
        "currency": "USD",
        "bid": 199.9,
        "ask": 200.1,
        "spread_absolute": 0.2,
        "spread_percentage": 0.001,
        "volume": 1000.0,
        "market_timestamp": NOW - timedelta(seconds=30),
        "ingested_at": NOW,
        "provider": provider,
        "freshness_seconds": 30,
        "quality_status": "live",
        "note": note,
        "provider_status": ProviderStatus.available_status(provider, "market_quote", note),
    }
    values.update(overrides)
    return QuoteSnapshot(**values)


def _article(provider: str = "polygon") -> NormalizedNewsArticle:
    return NormalizedNewsArticle(
        article_id=f"{provider}-1",
        ticker="AAPL",
        exchange="US",
        source="Reuters",
        title="Apple reliability test",
        summary="Provider reliability test article.",
        url=f"https://example.com/{provider}",
        published_at=NOW - timedelta(minutes=20),
        ingested_at=NOW,
        provider=provider,
        dedupe_hash=f"hash-{provider}",
        relevance_score=1.0,
    )


def _candidate(provider: str, factory, *, configured=True) -> ProviderCandidate:
    return ProviderCandidate(
        provider=provider,
        service="test",
        supports_exchange=lambda exchange: exchange == "US",
        configured=lambda: configured,
        factory=factory,
        unconfigured_message=f"{provider} not configured",
    )


class CountingQuoteProvider:
    provider_name = "polygon"

    def __init__(self, *, fail_times: int = 0, exc: Exception | None = None, quote: QuoteSnapshot | None = None) -> None:
        self.calls = 0
        self.fail_times = fail_times
        self.exc = exc or requests.Timeout("slow")
        self.quote = quote or _quote()

    def fetch_quote_snapshot(self, symbol):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.exc
        return self.quote

    def fetch_price_bars(self, symbol, start, end, interval):
        return pd.DataFrame(
            [{"timestamp": NOW, "Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.5, "Volume": 1000.0}]
        ).set_index("timestamp")


class CountingNewsProvider:
    provider_name = "fallback_web"

    def __init__(self, *, fail_times: int = 0, exc: Exception | None = None, articles=None, leaf_provider="yahoo_html", data_mode="SCRAPED") -> None:
        self.calls = 0
        self.fail_times = fail_times
        self.exc = exc or requests.ConnectionError("offline")
        self.articles = articles if articles is not None else [_article("fallback_web")]
        self.leaf_provider = leaf_provider
        self.data_mode = data_mode

    def fetch_news(self, symbol, limit=20):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.exc
        return self.articles[:limit]


def test_timeout_retries_then_succeeds(monkeypatch) -> None:
    monkeypatch.setattr(settings, "provider_retry_count", 1)
    provider = CountingQuoteProvider(fail_times=1)
    router = MarketDataRouter(candidates=[_candidate("polygon", lambda: provider)], sleep=lambda _: None)
    symbol = registry.get("US", "AAPL")
    assert symbol is not None

    result = router.fetch_quote(symbol)

    assert result.available is True
    assert provider.calls == 2


def test_transient_5xx_retries(monkeypatch) -> None:
    monkeypatch.setattr(settings, "provider_retry_count", 1)
    response = requests.Response()
    response.status_code = 503
    provider = CountingQuoteProvider(fail_times=1, exc=requests.HTTPError(response=response))
    router = MarketDataRouter(candidates=[_candidate("polygon", lambda: provider)], sleep=lambda _: None)
    symbol = registry.get("US", "AAPL")
    assert symbol is not None

    result = router.fetch_quote(symbol)

    assert result.available is True
    assert provider.calls == 2


def test_auth_failure_does_not_retry(monkeypatch) -> None:
    monkeypatch.setattr(settings, "provider_retry_count", 2)
    response = requests.Response()
    response.status_code = 401
    provider = CountingQuoteProvider(fail_times=5, exc=requests.HTTPError(response=response))
    router = MarketDataRouter(candidates=[_candidate("polygon", lambda: provider)], sleep=lambda _: None)
    symbol = registry.get("US", "AAPL")
    assert symbol is not None

    result = router.fetch_quote(symbol)

    assert provider.calls == 1
    assert result.attempts[0].category == ProviderFailureCategory.AUTHENTICATION


def test_unconfigured_provider_does_not_call_factory() -> None:
    called = {"factory": False}

    def factory():
        called["factory"] = True
        return CountingQuoteProvider()

    router = MarketDataRouter(candidates=[_candidate("polygon", factory, configured=False)])
    symbol = registry.get("US", "AAPL")
    assert symbol is not None

    result = router.fetch_quote(symbol)

    assert called["factory"] is False
    assert result.attempts[0].category == ProviderFailureCategory.UNCONFIGURED


def test_rate_limit_classification_and_retry_after() -> None:
    response = requests.Response()
    response.status_code = 429
    response.headers["Retry-After"] = "17"
    exc = requests.HTTPError(response=response)

    assert classify_exception(exc) == ProviderFailureCategory.RATE_LIMIT
    assert retry_after_seconds(exc) == 17


def test_polygon_quote_mode_provenance() -> None:
    assert leaf_provider_for_quote(_quote(note="Polygon single-ticker snapshot")) == "polygon/snapshot"
    assert leaf_provider_for_quote(_quote(note="Polygon last trade fallback")) == "polygon/last_trade"
    assert leaf_provider_for_quote(_quote(note="Polygon previous-close fallback", quality_status="stale")) == "polygon/previous_close"


def test_news_leaf_provider_provenance_from_fallback() -> None:
    provider = CountingNewsProvider(leaf_provider="yahoo_html", data_mode="SCRAPED")
    router = NewsProviderRouter(candidates=[_candidate("fallback_web", lambda: provider)])
    symbol = registry.get("US", "AAPL")
    assert symbol is not None

    result = router.fetch_news(symbol, limit=5)

    assert result.provider == "fallback_web"
    assert result.leaf_provider == "yahoo_html"
    assert result.data_mode == DataMode.SCRAPED


def test_quote_validation_rejects_bad_values() -> None:
    assert "price must be finite and greater than zero" in validate_quote_snapshot(_quote(current_price=-1.0))
    assert "price must be finite and greater than zero" in validate_quote_snapshot(_quote(current_price=float("nan")))
    assert "bid cannot exceed ask" in validate_quote_snapshot(_quote(bid=201.0, ask=200.0))
    assert "volume cannot be negative or malformed" in validate_quote_snapshot(_quote(volume=-1.0))


def test_bars_validation_rejects_invalid_ohlc_and_duplicates() -> None:
    frame = pd.DataFrame(
        [
            {"timestamp": NOW, "Open": 100.0, "High": 99.0, "Low": 98.0, "Close": 100.0, "Volume": 100.0},
            {"timestamp": NOW, "Open": 100.0, "High": 101.0, "Low": 102.0, "Close": 100.0, "Volume": -1.0},
        ]
    ).set_index("timestamp")

    reasons = validate_bars_frame(frame)

    assert "duplicate bar timestamps" in reasons
    assert "high must be at least open and close" in reasons
    assert "low must be at most open and close" in reasons
    assert "volume cannot be negative" in reasons


def test_news_validation_excludes_malformed_record() -> None:
    valid, reasons = validate_news_articles([
        _article(),
        _article().__class__(
            article_id="bad",
            ticker="AAPL",
            exchange="US",
            source="",
            title="",
            summary=None,
            url="not-a-url",
            published_at=NOW,
            ingested_at=NOW,
            provider="polygon",
            dedupe_hash="bad",
        ),
    ])

    assert len(valid) == 1
    assert "article title is empty" in reasons


def test_freshness_model_fresh_aging_stale_unknown() -> None:
    assert assess_freshness(NOW - timedelta(seconds=30), NOW, DataMode.LIVE) == FreshnessLabel.FRESH
    assert assess_freshness(NOW - timedelta(minutes=5), NOW, DataMode.LIVE) == FreshnessLabel.AGING
    assert assess_freshness(NOW - timedelta(hours=3), NOW, DataMode.LIVE) == FreshnessLabel.STALE
    assert assess_freshness(None, NOW, DataMode.LIVE) == FreshnessLabel.UNKNOWN


def test_ttl_cache_hit_and_expiration() -> None:
    current = {"now": NOW}
    cache = ProviderTTLCache(clock=lambda: current["now"])
    cache.set(("quote", "AAPL"), CacheEntry(_quote(), "polygon", "polygon/snapshot", DataMode.LIVE, NOW, NOW))

    assert cache.get(("quote", "AAPL"), 60) is not None
    current["now"] = NOW + timedelta(seconds=61)
    assert cache.get(("quote", "AAPL"), 60) is None
    assert cache.get_stale(("quote", "AAPL")) is not None


def test_router_cache_hit_preserves_provenance() -> None:
    provider = CountingQuoteProvider()
    router = MarketDataRouter(candidates=[_candidate("polygon", lambda: provider)])
    symbol = registry.get("US", "AAPL")
    assert symbol is not None

    first = router.fetch_quote(symbol)
    second = router.fetch_quote(symbol)

    assert first.from_cache is False
    assert second.from_cache is True
    assert second.leaf_provider == "polygon/snapshot"
    assert provider.calls == 1


def test_stale_cache_degraded_fallback_after_live_failure() -> None:
    cache = ProviderTTLCache(clock=lambda: NOW + timedelta(hours=2))
    cache.set(("quote", "us-aapl"), CacheEntry(_quote(), "polygon", "polygon/snapshot", DataMode.LIVE, NOW, NOW))
    provider = CountingQuoteProvider(fail_times=5)
    router = MarketDataRouter(candidates=[_candidate("polygon", lambda: provider)], cache=cache, sleep=lambda _: None)
    symbol = registry.get("US", "AAPL")
    assert symbol is not None

    result = router.fetch_quote(symbol)

    assert result.from_cache is True
    assert result.status.status == DataSourceState.STALE
    assert result.attempts[-1].category == ProviderFailureCategory.STALE_DATA


def test_data_quality_labels_for_live_previous_close_scraped_and_unavailable() -> None:
    high = assess_quote_quality(_quote(), provider="polygon", mode=DataMode.LIVE, fetched_at=NOW)
    previous = assess_quote_quality(
        _quote(note="Polygon previous-close fallback", quality_status="stale", freshness_seconds=86_400, market_timestamp=NOW - timedelta(days=1)),
        provider="polygon",
        mode=DataMode.PREVIOUS_CLOSE,
        fetched_at=NOW,
    )
    unavailable = assess_quote_quality(None, provider="polygon", mode=DataMode.UNKNOWN, fetched_at=NOW)
    scraped = assess_news_quality([_article("fallback_web")], provider="fallback_web", mode=DataMode.SCRAPED, source_timestamp=NOW - timedelta(minutes=10), fallback_used=True, fetched_at=NOW)

    assert high.label == DataQualityLabel.HIGH
    assert previous.label in {DataQualityLabel.MEDIUM, DataQualityLabel.LOW}
    assert unavailable.label == DataQualityLabel.UNAVAILABLE
    assert scraped.label in {DataQualityLabel.MEDIUM, DataQualityLabel.LOW}


def test_provider_health_tracks_success_failure_and_fallback() -> None:
    health = ProviderHealthRegistry(clock=lambda: NOW)
    health.record(provider="polygon", service="news", configured=True, status=DataSourceState.AVAILABLE)
    health.record(provider="marketaux", service="news", configured=True, status=DataSourceState.UNAVAILABLE, failure_category=ProviderFailureCategory.TIMEOUT, fallback_used=True)

    records = {(row.provider, row.service): row for row in health.snapshot()}

    assert records[("polygon", "news")].last_successful_fetch == NOW
    assert records[("marketaux", "news")].last_failure_category == ProviderFailureCategory.TIMEOUT
    assert records[("marketaux", "news")].recent_fallback_used is True


def test_signal_v1_still_sees_valid_live_quote_as_usable() -> None:
    assert is_usable_quote_snapshot(_quote())
