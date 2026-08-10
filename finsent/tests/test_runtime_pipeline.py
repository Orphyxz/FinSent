from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from finsent.app.database.base import Base
from finsent.app.database.repository import NewsRepository
from finsent.app.models.schemas import MarketSignalSnapshot
from finsent.app.services.llm_analyzers import GeminiNewsAnalyzer
from finsent.app.services.market_providers import KiteMarketDataProvider
from finsent.app.services.news_providers import MarketauxNewsProvider, NormalizedNewsArticle, build_news_provider
from finsent.app.services.symbol_registry import registry
from finsent.app.dashboard.view_model import DashboardState, build_focus_status_banner, build_news_table


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def test_polygon_style_news_persistence_feeds_news_table() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)

    symbol = registry.get("US", "AAPL")
    assert symbol is not None
    article = NormalizedNewsArticle(
        article_id="article-1",
        ticker="AAPL",
        exchange="US",
        source="Reuters",
        title="Apple launches new AI workflow",
        summary="A fresh product catalyst for the next few sessions.",
        url="https://example.com/apple-ai",
        published_at=_utc_now() - timedelta(minutes=12),
        ingested_at=_utc_now(),
        provider="polygon",
        dedupe_hash="hash-1",
        relevance_score=1.0,
    )

    analyzer = GeminiNewsAnalyzer()
    analysis = analyzer.analyze_article(symbol, article)
    analysis = analysis.__class__(
        relevant=True,
        sentiment="bullish",
        confidence=0.82,
        impact_strength=0.64,
        time_horizon="1-3d",
        catalyst_tag="product",
        short_reason="Product launch is a near-term catalyst.",
        provider="gemini",
        parse_status="ok",
    )

    with Session() as session:
        repo = NewsRepository(session)
        repo.upsert_normalized_news(symbol, article, analysis)
        session.commit()
        stored = repo.list_news_df("AAPL", "US")

    assert not stored.empty
    assert stored.iloc[0]["provider"] == "polygon"
    assert stored.iloc[0]["source"] == "Reuters"
    assert stored.iloc[0]["analysis_provider"] == "gemini"

    table = build_news_table(pd.DataFrame(), stored)
    assert "Provider" in table.columns
    assert "Age" in table.columns
    assert "Catalyst" in table.columns
    assert "Parse Status" in table.columns
    assert table.iloc[0]["Provider"] == "polygon"
    assert table.iloc[0]["Catalyst"] == "product"
    assert table.iloc[0]["Parse Status"] == "ok"


def test_gemini_analysis_handles_malformed_numeric_json_safely() -> None:
    symbol = registry.get("US", "AAPL")
    assert symbol is not None
    article = NormalizedNewsArticle(
        article_id="article-2",
        ticker="AAPL",
        exchange="US",
        source="Reuters",
        title="Apple comment",
        summary="Summary",
        url="https://example.com/apple-comment",
        published_at=_utc_now(),
        ingested_at=_utc_now(),
        provider="polygon",
        dedupe_hash="hash-2",
        relevance_score=1.0,
    )

    analyzer = GeminiNewsAnalyzer()

    class StubClient:
        configured = True

        @staticmethod
        def generate_json(*args, **kwargs):
            return {
                "relevant": True,
                "sentiment": "bullish",
                "confidence": "not-a-number",
                "impact_strength": {"bad": "shape"},
                "time_horizon": "weird",
                "catalyst_tag": "unknown-tag",
                "short_reason": "Malformed values should not crash parsing.",
            }

    analyzer.client = StubClient()
    result = analyzer.analyze_article(symbol, article)

    assert result.sentiment == "bullish"
    assert result.confidence == 0.0
    assert result.impact_strength == 0.0
    assert result.time_horizon == "1-3d"
    assert result.catalyst_tag == "other"
    assert result.parse_status == "ok"


def test_kite_historical_bars_normalize_to_ohlcv_frame() -> None:
    symbol = registry.get("NSE", "TCS")
    assert symbol is not None

    class StubResponse:
        def __init__(self, text: str = "", payload: dict | None = None):
            self.text = text
            self._payload = payload or {}

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class StubSession:
        def get(self, url, **kwargs):
            if url.endswith("/instruments"):
                csv_text = "instrument_token,exchange,tradingsymbol\n12345,NSE,TCS\n"
                return StubResponse(text=csv_text)
            if "/historical/" in url:
                return StubResponse(
                    payload={
                        "data": {
                            "candles": [
                                ["2026-04-23T09:15:00+05:30", 3500, 3510, 3490, 3505, 1000],
                                ["2026-04-23T09:30:00+05:30", 3505, 3520, 3500, 3518, 1200],
                            ]
                        }
                    }
                )
            raise AssertionError(f"Unexpected URL: {url}")

    provider = KiteMarketDataProvider()
    provider.session = StubSession()

    from finsent.app.config.settings import settings

    original_key = settings.kite_api_key
    original_token = settings.kite_access_token
    try:
        settings.kite_api_key = "test-key"
        settings.kite_access_token = "test-token"
        KiteMarketDataProvider._instrument_cache = None
        frame = provider.fetch_price_bars(symbol, datetime(2026, 4, 23, 9, 15), datetime(2026, 4, 23, 10, 0), "15m")
    finally:
        settings.kite_api_key = original_key
        settings.kite_access_token = original_token
        KiteMarketDataProvider._instrument_cache = None

    assert not frame.empty
    assert list(frame.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert float(frame.iloc[0]["Open"]) == 3500.0
    assert float(frame.iloc[1]["Close"]) == 3518.0


def test_india_status_banner_shows_live_quote_but_missing_bars_and_fallback_news() -> None:
    state = DashboardState(
        news_df=pd.DataFrame(
            [
                {
                    "ticker": "NSE:TCS",
                    "provider": "fallback_web",
                    "source": "Yahoo Finance",
                    "published_at": _utc_now() - timedelta(minutes=8),
                    "parse_status": "ok",
                    "title": "TCS headline",
                }
            ]
        ),
        price_df=pd.DataFrame(),
        event_df=pd.DataFrame(),
        daily_summary_df=pd.DataFrame(),
        compare_df=pd.DataFrame(
            [
                {
                    "ticker": "NSE:TCS",
                    "mode": "Quote-quality fallback",
                    "quote_quality": "live",
                    "exchange": "NSE",
                }
            ]
        ),
        sector_df=pd.DataFrame(),
        snapshot_map={
            "NSE:TCS": MarketSignalSnapshot(
                bid=3499.0,
                ask=3501.0,
                bid_ask_spread=2.0,
                spread_pct=0.00057,
                volume_ratio=1.0,
                buy_sell_ratio=1.0,
                buy_pressure=0.0,
                market_signal=0.0,
                last_price=3500.0,
                price_timestamp=_utc_now(),
            )
        },
        quote_meta_map={
            "NSE:TCS": {
                "provider": "kite",
                "quality_status": "live",
                "current_price": 3500.0,
                "market_timestamp": _utc_now() - timedelta(seconds=15),
                "ingested_at": _utc_now(),
                "freshness_seconds": 15,
            }
        },
        signal_meta_map={"NSE:TCS": {"mode": "Quote-quality fallback"}},
        demo_mode=False,
        data_status="NSE quote is live, but historical bars are unavailable for overlap analysis. News quality is fallback-quality.",
    )

    banner = build_focus_status_banner("NSE:TCS", state)
    rendered = str(banner)

    assert "Bars status: unavailable" in rendered
    assert "News tier: fallback-quality" in rendered
    assert "Mode: Quote-quality fallback" in rendered
    assert "Price source: kite" in rendered


def test_marketaux_india_news_provider_normalizes_symbol_mapping_and_relevance() -> None:
    from finsent.app.config.settings import settings

    symbol = registry.get("NSE", "TCS")
    assert symbol is not None

    class StubResponse:
        def __init__(self, payload: dict):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class StubSession:
        def __init__(self):
            self.calls = 0

        def get(self, url, params=None, **kwargs):
            self.calls += 1
            if self.calls == 1:
                assert "TCS.NS" in params["symbols"]
                return StubResponse(
                    {
                        "data": [
                            {
                                "uuid": "m1",
                                "title": "TCS wins large outsourcing deal",
                                "url": "https://example.com/tcs-deal",
                                "published_at": "2026-04-23T09:30:00Z",
                                "source": "Economic Times",
                                "description": "New contract win.",
                                "entities": [{"symbol": "TCS.NS", "name": "Tata Consultancy Services"}],
                            }
                        ]
                    }
                )
            raise AssertionError("Company-name fallback should not be called when symbol match succeeds")

    provider = MarketauxNewsProvider()
    provider.session = StubSession()
    original_token = settings.marketaux_api_token
    try:
        settings.marketaux_api_token = "test-marketaux"
        articles = provider.fetch_news(symbol, limit=5)
    finally:
        settings.marketaux_api_token = original_token

    assert len(articles) == 1
    assert articles[0].provider == "marketaux"
    assert articles[0].source == "Economic Times"
    assert articles[0].ticker == "TCS"
    assert articles[0].exchange == "NSE"
    assert articles[0].relevance_score == 1.0


def test_build_news_provider_uses_marketaux_for_india_when_configured() -> None:
    from finsent.app.config.settings import settings

    symbol = registry.get("BSE", "TCS")
    assert symbol is not None
    original_token = settings.marketaux_api_token
    try:
        settings.marketaux_api_token = "test-marketaux"
        provider = build_news_provider(symbol)
    finally:
        settings.marketaux_api_token = original_token

    assert provider.provider_name == "marketaux"
