from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from finsent.app.config.settings import settings
from finsent.app.dashboard.app import create_app
from finsent.app.dashboard.view_model import build_compare_frame
from finsent.app.dashboard.view_model import _parse_provider_note
from finsent.app.database.base import SessionLocal
from finsent.app.database.repository import QuoteSnapshotRepository
from finsent.app.services.intelligence_service import IntelligenceService
from finsent.app.services.llm_analyzers import ArticleAnalysis
from finsent.app.services.market_providers import AlpacaMarketDataProvider, QuoteSnapshot, classify_us_market_status
from finsent.app.services.news_providers import AlpacaNewsProvider, NormalizedNewsArticle
from finsent.app.services.provider_routers import MarketDataRouter
from finsent.app.services.signal_engine import CompositeSignalEngine
from finsent.app.services.signal_service_v2 import SignalEngineV2Service
from finsent.app.services.symbol_registry import registry


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import requests

            response = requests.Response()
            response.status_code = self.status_code
            raise requests.HTTPError("request failed", response=response)

    def json(self) -> dict:
        return self.payload


class RecordingSession:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    def get(self, url: str, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return FakeResponse(self.payload)


def test_alpaca_snapshot_normalization_uses_iex_feed(monkeypatch) -> None:
    monkeypatch.setattr(settings, "alpaca_api_key", "key")
    monkeypatch.setattr(settings, "alpaca_api_secret", "secret")
    monkeypatch.setattr(settings, "alpaca_feed", "iex")
    provider = AlpacaMarketDataProvider()
    provider.session = RecordingSession(
        {
            "snapshots": {
                "AAPL": {
                    "latestTrade": {"p": 210.5, "t": "2026-08-10T15:59:50Z"},
                    "latestQuote": {"bp": 210.4, "ap": 210.6, "t": "2026-08-10T15:59:49Z"},
                    "minuteBar": {"o": 210.0, "h": 211.0, "l": 209.8, "c": 210.5, "v": 1200, "t": "2026-08-10T15:59:00Z"},
                    "dailyBar": {"o": 205.0, "h": 211.0, "l": 204.5, "c": 210.5, "v": 500000, "t": "2026-08-10T04:00:00Z"},
                    "prevDailyBar": {"c": 200.0, "t": "2026-08-09T04:00:00Z"},
                }
            }
        }
    )

    snapshot = provider.fetch_quote_snapshot(registry.get("US", "AAPL"))

    assert provider.session.calls[0]["params"]["feed"] == "iex"
    assert snapshot.provider == "alpaca"
    assert snapshot.feed == "iex"
    assert snapshot.current_price == 210.5
    assert snapshot.previous_close == 200.0
    assert snapshot.absolute_change == 10.5
    assert round(snapshot.percent_change or 0.0, 4) == 0.0525


def test_provider_note_parser_extracts_alpaca_feed_and_market_status() -> None:
    parsed = _parse_provider_note("Alpaca snapshot feed=iex; LIVE; market_status=MARKET OPEN")

    assert parsed["feed"] == "iex"
    assert parsed["market_status"] == "MARKET OPEN"


def test_missing_alpaca_credentials_are_reported_without_secrets(monkeypatch) -> None:
    monkeypatch.setattr(settings, "alpaca_api_key", "")
    monkeypatch.setattr(settings, "alpaca_api_secret", "")
    router = MarketDataRouter(candidates=None)
    symbol = registry.get("US", "AAPL")

    result = router.fetch_quote(symbol)

    assert any(attempt.provider == "alpaca" and attempt.category and attempt.category.value == "UNCONFIGURED" for attempt in result.attempts)
    assert "key123" not in " ".join(attempt.message.lower() for attempt in result.attempts)


def test_market_hours_labels_closed_premarket_open_and_after_hours() -> None:
    assert classify_us_market_status(datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)) == "PRE-MARKET"
    assert classify_us_market_status(datetime(2026, 8, 10, 15, 0, tzinfo=timezone.utc)) == "MARKET OPEN"
    assert classify_us_market_status(datetime(2026, 8, 10, 21, 0, tzinfo=timezone.utc)) == "AFTER-HOURS"
    assert classify_us_market_status(datetime(2026, 8, 9, 15, 0, tzinfo=timezone.utc)) == "MARKET CLOSED"


def test_alpaca_news_normalization_and_live_dedupe(monkeypatch) -> None:
    monkeypatch.setattr(settings, "alpaca_api_key", "key")
    monkeypatch.setattr(settings, "alpaca_api_secret", "secret")
    provider = AlpacaNewsProvider()
    provider.session = RecordingSession(
        {
            "news": [
                {"id": 1, "headline": "Apple launches product", "summary": "AAPL event", "url": "https://example.com/a?utm_source=x", "source": "Benzinga", "created_at": "2026-08-10T15:30:00Z"},
                {"id": 2, "headline": "Apple launches product", "summary": "AAPL event", "url": "https://example.com/a", "source": "Benzinga", "created_at": "2026-08-10T15:35:00Z"},
            ]
        }
    )

    articles = provider.fetch_news(registry.get("US", "AAPL"), limit=10)
    deduped = IntelligenceService._dedupe(articles)

    assert provider.session.calls[0]["url"].endswith("/v1beta1/news")
    assert articles[0].provider == "alpaca"
    assert len(deduped) == 1


def test_live_signal_v1_and_v2_construct_from_current_inputs() -> None:
    symbol = registry.get("US", "AAPL")
    article = _article(symbol.ticker)
    analysis = ArticleAnalysis(True, "bullish", 0.8, 0.6, "intraday", "product", "FinBERT positive.", "finbert", "ok")
    quote = _quote(symbol.ticker)
    bars = pd.DataFrame(
        [
            {"Open": 100, "High": 101, "Low": 99, "Close": 100, "Volume": 1000},
            {"Open": 101, "High": 103, "Low": 100, "Close": 102, "Volume": 1400},
            {"Open": 102, "High": 106, "Low": 102, "Close": 105, "Volume": 2200},
        ],
        index=pd.to_datetime(["2026-08-10 14:30", "2026-08-10 14:45", "2026-08-10 15:00"]),
    )

    v1 = CompositeSignalEngine().compute(quote, [(article, analysis)], IntelligenceService().llm.aggregate(symbol, [(article, analysis)]))
    v2_input = SignalEngineV2Service().build_input(instrument=symbol, news_pairs=[(article, analysis)], quote=quote, price_bars=bars)
    v2 = SignalEngineV2Service().evaluate(v2_input).result

    assert v1.mode == "News + Quote Quality"
    assert v2.signal_mode == "NEWS_PLUS_MARKET"
    assert {component.name for component in v2.components}.issuperset({"news", "price_momentum", "volume_confirmation", "freshness"})


def test_compare_frame_keeps_successful_symbol_when_peer_fails() -> None:
    news_df = pd.DataFrame([{"ticker": "AAPL", "published_at": pd.Timestamp("2026-08-10T15:00:00"), "sentiment_score": 0.5, "model_confidence": 0.8, "signal_confidence": 0.8, "sentiment_label": "bullish", "title": "AAPL news"}])
    price_df = pd.DataFrame([{"ticker": "AAPL", "timestamp": pd.Timestamp("2026-08-10T15:00:00"), "open": 100, "high": 102, "low": 99, "close": 101, "volume": 1000}])
    quote_meta = {
        "AAPL": {"provider": "alpaca", "quality_status": "live", "current_price": 101, "market_timestamp": datetime(2026, 8, 10, 15, 0), "currency": "USD", "market_status": "MARKET OPEN", "freshness_label": "LIVE", "feed": "iex"},
        "META": {"provider": "alpaca", "quality_status": "unavailable", "note": "Alpaca rate limited", "market_status": "UNKNOWN"},
    }

    frame = build_compare_frame(news_df, price_df, pd.DataFrame(), quote_meta_map=quote_meta)

    assert set(frame["ticker"]) == {"AAPL", "META"}
    assert frame.loc[frame["ticker"] == "AAPL", "quote_quality"].iloc[0] == "live"
    assert frame.loc[frame["ticker"] == "META", "quote_quality"].iloc[0] == "unavailable"


def test_compare_callback_renders_aapl_nvda_tsla_without_shape_error() -> None:
    app = create_app()
    client = app.server.test_client()
    output_key = next(key for key in app.callback_map if "compare-selection-summary" in key)
    payload = {
        "output": output_key,
        "outputs": [
            {"id": "compare-selection-summary", "property": "children"},
            {"id": "compare-empty-state", "property": "children"},
            {"id": "compare-empty-state", "property": "style"},
            {"id": "compare-content", "property": "style"},
            {"id": "compare-metric-row", "property": "children"},
            {"id": "compare-main-chart", "property": "figure"},
            {"id": "compare-secondary-chart", "property": "figure"},
            {"id": "compare-ai-summary", "property": "children"},
        ],
        "inputs": [
            {
                "id": "selection-store",
                "property": "data",
                "value": {
                    "focus_ticker": "AAPL",
                    "exchange_filter": "US",
                    "compare_tickers": ["NVDA", "TSLA"],
                    "horizon": "medium",
                    "date_window": "30d",
                    "alert_threshold": 40,
                    "analysis_ready": True,
                },
            },
            {"id": "live-refresh-store", "property": "data", "value": None},
        ],
        "state": [],
        "changedPropIds": ["selection-store.data"],
    }

    response = client.post("/_dash-update-component", json=payload)

    assert response.status_code == 200
    body = response.get_json()["response"]
    assert body["compare-content"]["style"] == {"display": "block"}
    assert len(body["compare-main-chart"]["figure"]["data"]) >= 1
    assert len(body["compare-secondary-chart"]["figure"]["data"]) >= 1


def test_quote_snapshot_upsert_reuses_duplicate_provider_timestamp() -> None:
    symbol = registry.get("US", "AAPL")
    timestamp = datetime(2099, 1, 2, 15, 30)
    first = _quote(symbol.ticker)
    first.market_timestamp = timestamp
    first.current_price = 101.0
    second = _quote(symbol.ticker)
    second.market_timestamp = timestamp
    second.current_price = 102.0

    with SessionLocal() as session:
        repo = QuoteSnapshotRepository(session)
        first_row = repo.upsert_quote_snapshot(symbol, first)
        first_id = first_row.id
        second_row = repo.upsert_quote_snapshot(symbol, second)

        assert second_row.id == first_id
        assert second_row.current_price == 102.0
        session.rollback()


def _article(ticker: str) -> NormalizedNewsArticle:
    return NormalizedNewsArticle(
        article_id="a1",
        ticker=ticker,
        exchange="US",
        source="Benzinga",
        title=f"{ticker} launches new product",
        summary="Current market headline",
        url="https://example.com/a1",
        published_at=datetime(2026, 8, 10, 15, 0),
        ingested_at=datetime(2026, 8, 10, 15, 1),
        provider="alpaca",
        dedupe_hash="a1",
        relevance_score=1.0,
    )


def _quote(ticker: str) -> QuoteSnapshot:
    return QuoteSnapshot(
        symbol=ticker,
        exchange="US",
        provider_symbol=ticker,
        current_price=105.0,
        currency="USD",
        bid=104.9,
        ask=105.1,
        spread_absolute=0.2,
        spread_percentage=0.0019,
        volume=2200,
        market_timestamp=datetime(2026, 8, 10, 15, 0),
        ingested_at=datetime(2026, 8, 10, 15, 0),
        provider="alpaca",
        freshness_seconds=10,
        quality_status="live",
        note="Alpaca snapshot feed=iex; LIVE; market_status=MARKET OPEN",
        feed="iex",
        market_status="MARKET OPEN",
        freshness_label="LIVE",
    )
