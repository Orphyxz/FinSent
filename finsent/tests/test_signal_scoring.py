from __future__ import annotations

from datetime import datetime, timedelta, timezone

from finsent.app.services.llm_analyzers import AggregateAnalysis, ArticleAnalysis
from finsent.app.services.market_providers import QuoteSnapshot
from finsent.app.services.news_providers import NormalizedNewsArticle
from finsent.app.services.signal_engine import CompositeSignalEngine


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def test_composite_signal_is_deterministic_app_logic() -> None:
    quote = QuoteSnapshot(
        symbol="AAPL",
        exchange="US",
        provider_symbol="AAPL",
        current_price=201.5,
        currency="USD",
        bid=201.4,
        ask=201.6,
        spread_absolute=0.2,
        spread_percentage=0.00099,
        volume=1_000_000.0,
        market_timestamp=_utc_now() - timedelta(seconds=20),
        ingested_at=_utc_now(),
        provider="polygon",
        freshness_seconds=20,
        quality_status="live",
        note="test",
    )
    article = NormalizedNewsArticle(
        article_id="1",
        ticker="AAPL",
        exchange="US",
        source="Reuters",
        title="Apple beats expectations",
        summary="Strong quarter",
        url="https://example.com/aapl",
        published_at=_utc_now() - timedelta(minutes=20),
        ingested_at=_utc_now(),
        provider="polygon",
        dedupe_hash="hash-1",
        relevance_score=1.0,
    )
    analysis = ArticleAnalysis(
        relevant=True,
        sentiment="bullish",
        confidence=0.9,
        impact_strength=0.8,
        time_horizon="1-3d",
        catalyst_tag="earnings",
        short_reason="Positive earnings surprise.",
        provider="gemini",
        parse_status="ok",
    )
    aggregate = AggregateAnalysis(
        overall_sentiment="bullish",
        overall_confidence=0.9,
        net_short_term_view="bullish short-term signal",
        action_bias="buy",
        final_reason="Positive earnings surprise.",
        provider="gemini",
    )

    signal = CompositeSignalEngine().compute(quote, [(article, analysis)], aggregate)

    assert signal.composite_label == "bullish"
    assert signal.composite_score > 0
    assert signal.signal_confidence > 0
    assert signal.mode == "News + Quote Quality"


def test_composite_signal_market_only_mode_is_explicit() -> None:
    quote = QuoteSnapshot(
        symbol="TCS",
        exchange="NSE",
        provider_symbol="NSE:TCS",
        current_price=3500.0,
        currency="INR",
        bid=3499.0,
        ask=3501.0,
        spread_absolute=2.0,
        spread_percentage=2.0 / 3500.0,
        volume=500_000.0,
        market_timestamp=_utc_now() - timedelta(seconds=30),
        ingested_at=_utc_now(),
        provider="kite",
        freshness_seconds=30,
        quality_status="live",
        note="test",
    )
    aggregate = AggregateAnalysis(
        overall_sentiment="neutral",
        overall_confidence=0.0,
        net_short_term_view="no strong edge",
        action_bias="watch",
        final_reason="No fresh articles",
        provider="gemini",
    )

    signal = CompositeSignalEngine().compute(quote, [], aggregate)

    assert signal.mode == "Quote-quality fallback"
    assert signal.composite_label in {"neutral", "bullish", "bearish"}
