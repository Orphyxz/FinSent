from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest
import requests

from finsent.app.config.settings import settings
from finsent.app.services.kaggle_data import load_nse_price_frame, load_us_price_frames
from finsent.app.services.market_providers import QuoteSnapshot, is_usable_quote_snapshot
from finsent.app.services.news_providers import NormalizedNewsArticle
from finsent.app.services.provider_contracts import (
    ProviderCandidate,
    ProviderFailureCategory,
    classify_exception,
)
from finsent.app.services.provider_routers import MarketDataRouter, NewsProviderRouter, default_market_candidates
from finsent.app.services.provider_status import DataSourceState, ProviderStatus
from finsent.app.services.symbol_registry import registry


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _quote(provider: str = "primary", **overrides) -> QuoteSnapshot:
    now = _now()
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
        "volume": 1_000_000.0,
        "market_timestamp": now - timedelta(seconds=30),
        "ingested_at": now,
        "provider": provider,
        "freshness_seconds": 30,
        "quality_status": "live",
        "note": "test quote",
        "provider_status": ProviderStatus.available_status(provider, "market_quote", "test quote"),
    }
    values.update(overrides)
    return QuoteSnapshot(**values)


def _article(provider: str = "primary_news") -> NormalizedNewsArticle:
    now = _now()
    return NormalizedNewsArticle(
        article_id=f"{provider}-1",
        ticker="AAPL",
        exchange="US",
        source="Reuters",
        title="Apple provider routing works",
        summary="Router test.",
        url=f"https://example.com/{provider}",
        published_at=now - timedelta(minutes=10),
        ingested_at=now,
        provider=provider,
        dedupe_hash=f"hash-{provider}",
        relevance_score=1.0,
    )


def _candidate(provider: str, factory, *, configured=True, exchanges=None) -> ProviderCandidate:
    supported = set(exchanges or {"US"})
    return ProviderCandidate(
        provider=provider,
        service="test",
        supports_exchange=lambda exchange: exchange in supported,
        configured=lambda: configured,
        factory=factory,
        unconfigured_message=f"{provider} missing config",
    )


class QuoteProvider:
    provider_name = "primary"

    def __init__(self, quote: QuoteSnapshot | None = None, exc: Exception | None = None) -> None:
        self.quote = quote or _quote(self.provider_name)
        self.exc = exc

    def fetch_quote_snapshot(self, symbol):
        if self.exc is not None:
            raise self.exc
        return self.quote

    def fetch_price_bars(self, symbol, start, end, interval):
        if self.exc is not None:
            raise self.exc
        return pd.DataFrame(
            [{"timestamp": datetime(2026, 8, 9, 10, 0), "Open": 1.0, "High": 2.0, "Low": 1.0, "Close": 1.5, "Volume": 100.0}]
        ).set_index("timestamp")


class NewsProvider:
    provider_name = "primary_news"

    def __init__(self, articles=None, exc: Exception | None = None) -> None:
        self.articles = articles if articles is not None else [_article(self.provider_name)]
        self.exc = exc
        self.seen_limit = None

    def fetch_news(self, symbol, limit=20):
        self.seen_limit = limit
        if self.exc is not None:
            raise self.exc
        return self.articles[:limit]


def test_market_router_primary_succeeds() -> None:
    symbol = registry.get("US", "AAPL")
    assert symbol is not None
    router = MarketDataRouter(candidates=[_candidate("primary", lambda: QuoteProvider(_quote("primary")))])

    result = router.fetch_quote(symbol)

    assert result.provider == "primary"
    assert result.available is True
    assert result.fallback_used is False
    assert result.attempts[-1].selected is True
    assert is_usable_quote_snapshot(result.data)


def test_market_router_primary_unconfigured_fallback_succeeds() -> None:
    symbol = registry.get("US", "AAPL")
    assert symbol is not None
    router = MarketDataRouter(
        candidates=[
            _candidate("primary", lambda: QuoteProvider(), configured=False),
            _candidate("fallback", lambda: QuoteProvider(_quote("fallback"))),
        ]
    )

    result = router.fetch_quote(symbol)

    assert result.provider == "fallback"
    assert result.fallback_used is True
    assert result.attempts[0].category == ProviderFailureCategory.UNCONFIGURED
    assert result.attempts[-1].selected is True


def test_market_router_primary_fails_fallback_succeeds() -> None:
    symbol = registry.get("US", "AAPL")
    assert symbol is not None
    router = MarketDataRouter(
        candidates=[
            _candidate("primary", lambda: QuoteProvider(exc=requests.Timeout("slow"))),
            _candidate("fallback", lambda: QuoteProvider(_quote("fallback"))),
        ]
    )

    result = router.fetch_quote(symbol)

    assert result.provider == "fallback"
    assert result.attempts[0].category == ProviderFailureCategory.TIMEOUT
    assert result.fallback_used is True


def test_market_router_all_providers_fail_returns_structured_unavailable_quote() -> None:
    symbol = registry.get("US", "AAPL")
    assert symbol is not None
    router = MarketDataRouter(candidates=[_candidate("primary", lambda: QuoteProvider(exc=requests.ConnectionError("offline")))])

    result = router.fetch_quote(symbol)

    assert result.available is False
    assert result.provider == "unavailable"
    assert result.status.status == DataSourceState.UNAVAILABLE
    assert result.data is not None
    assert not is_usable_quote_snapshot(result.data)


def test_market_router_unusable_quote_falls_back() -> None:
    symbol = registry.get("US", "AAPL")
    assert symbol is not None
    bad_quote = _quote("primary", current_price=None, market_timestamp=None, quality_status="unavailable")
    bad_quote.provider_status = ProviderStatus.unavailable("primary", "market_quote", "no price")
    router = MarketDataRouter(
        candidates=[
            _candidate("primary", lambda: QuoteProvider(bad_quote)),
            _candidate("fallback", lambda: QuoteProvider(_quote("fallback"))),
        ]
    )

    result = router.fetch_quote(symbol)

    assert result.provider == "fallback"
    assert result.attempts[0].category == ProviderFailureCategory.NO_DATA


def test_market_router_unsupported_market_is_explicit() -> None:
    symbol = registry.get("US", "AAPL")
    assert symbol is not None
    unsupported_symbol = symbol.__class__(
        internal_id="x",
        ticker="XYZ",
        display_name="Unsupported",
        exchange="LSE",
        provider_symbol="LSE:XYZ",
        ui_label="XYZ",
        sector="Other",
    )
    router = MarketDataRouter(candidates=[_candidate("primary", lambda: QuoteProvider(), exchanges={"US"})])

    result = router.fetch_quote(unsupported_symbol)

    assert result.provider == "unavailable"
    assert result.attempts[-1].category == ProviderFailureCategory.UNSUPPORTED_SYMBOL


def test_market_router_historical_bars_success_and_no_data() -> None:
    symbol = registry.get("US", "AAPL")
    assert symbol is not None
    router = MarketDataRouter(candidates=[_candidate("primary", lambda: QuoteProvider())])

    result = router.fetch_price_bars(symbol, start=datetime(2026, 8, 1), end=datetime(2026, 8, 9), interval="15m")

    assert result.provider == "primary"
    assert result.data is not None
    assert not result.data.empty
    assert result.status.status == DataSourceState.AVAILABLE


def test_news_router_primary_provider_and_limit_provenance() -> None:
    symbol = registry.get("US", "AAPL")
    assert symbol is not None
    provider = NewsProvider(articles=[_article("primary_news"), _article("primary_news_2")])
    router = NewsProviderRouter(candidates=[_candidate("primary_news", lambda: provider)])

    result = router.fetch_news(symbol, limit=1)

    assert result.provider == "primary_news"
    assert result.data is not None
    assert len(result.data) == 1
    assert provider.seen_limit == 1
    assert result.attempts[-1].selected is True


def test_news_router_unconfigured_primary_fallback_provider() -> None:
    symbol = registry.get("US", "AAPL")
    assert symbol is not None
    router = NewsProviderRouter(
        candidates=[
            _candidate("polygon", lambda: NewsProvider(), configured=False),
            _candidate("fallback_web", lambda: NewsProvider([_article("fallback_web")])),
        ]
    )

    result = router.fetch_news(symbol, limit=5)

    assert result.provider == "fallback_web"
    assert result.fallback_used is True
    assert result.attempts[0].category == ProviderFailureCategory.UNCONFIGURED
    assert result.data is not None
    assert result.data[0].provider == "fallback_web"


def test_news_router_all_fail_returns_no_data_result() -> None:
    symbol = registry.get("US", "AAPL")
    assert symbol is not None
    router = NewsProviderRouter(candidates=[_candidate("primary_news", lambda: NewsProvider(articles=[]))])

    result = router.fetch_news(symbol, limit=5)

    assert result.provider == "unavailable"
    assert result.data == []
    assert result.attempts[0].category == ProviderFailureCategory.NO_DATA
    assert result.attempts[-1].selected is True


def test_failure_classification_authentication_and_rate_limit() -> None:
    auth_response = requests.Response()
    auth_response.status_code = 401
    rate_response = requests.Response()
    rate_response.status_code = 429

    assert classify_exception(requests.Timeout("slow")) == ProviderFailureCategory.TIMEOUT
    assert classify_exception(requests.HTTPError(response=auth_response)) == ProviderFailureCategory.AUTHENTICATION
    assert classify_exception(requests.HTTPError(response=rate_response)) == ProviderFailureCategory.RATE_LIMIT


def test_default_market_candidates_route_us_nse_and_bse(monkeypatch) -> None:
    monkeypatch.setattr(settings, "polygon_api_key", "")
    monkeypatch.setattr(settings, "kite_api_key", "")
    monkeypatch.setattr(settings, "kite_access_token", "")
    candidates = default_market_candidates()

    assert [candidate.provider for candidate in candidates if candidate.supports_exchange("US")] == ["polygon"]
    assert [candidate.provider for candidate in candidates if candidate.supports_exchange("NSE")] == ["kite"]
    assert [candidate.provider for candidate in candidates if candidate.supports_exchange("BSE")] == ["kite"]


def test_historical_local_nse_data_policy_accepts_valid_csv(tmp_path) -> None:
    csv_path = tmp_path / "TCS.csv"
    csv_path.write_text(
        "Date,Open,High,Low,Close,Volume\n2026-08-07,100,110,90,105,1000\n",
        encoding="utf-8",
    )

    ticker, frame = load_nse_price_frame(csv_path)

    assert ticker == "TCS"
    assert list(frame.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert float(frame.iloc[0]["Close"]) == 105.0


def test_historical_us_data_policy_rejects_unavailable_local_data(tmp_path) -> None:
    missing_path = tmp_path / "missing.csv"

    with pytest.raises(FileNotFoundError):
        load_us_price_frames(missing_path)
