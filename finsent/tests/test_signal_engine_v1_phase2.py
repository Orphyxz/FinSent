from __future__ import annotations

from datetime import datetime, timedelta, timezone

from finsent.app.services.llm_analyzers import AggregateAnalysis, ArticleAnalysis
from finsent.app.services.market_providers import QuoteSnapshot
from finsent.app.services.news_providers import NormalizedNewsArticle
from finsent.app.services.provider_status import ProviderStatus
from finsent.app.services.signal_engine import CompositeSignalEngine


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _quote(**overrides) -> QuoteSnapshot:
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
        "provider": "polygon",
        "freshness_seconds": 30,
        "quality_status": "live",
        "note": "test",
        "provider_status": ProviderStatus.available_status("polygon", "market_quote", "test"),
    }
    values.update(overrides)
    return QuoteSnapshot(**values)


def _article(sentiment: str = "bullish", confidence: float = 0.9, impact: float = 0.8):
    now = _now()
    article = NormalizedNewsArticle(
        article_id=f"{sentiment}-1",
        ticker="AAPL",
        exchange="US",
        source="Reuters",
        title=f"AAPL {sentiment}",
        summary="test",
        url=f"https://example.com/{sentiment}",
        published_at=now - timedelta(minutes=10),
        ingested_at=now,
        provider="polygon",
        dedupe_hash=f"hash-{sentiment}",
        relevance_score=1.0,
    )
    analysis = ArticleAnalysis(
        relevant=True,
        sentiment=sentiment,
        confidence=confidence,
        impact_strength=impact,
        time_horizon="1-3d",
        catalyst_tag="other",
        short_reason="test",
        provider="gemini",
        parse_status="ok",
    )
    return article, analysis


def _aggregate(confidence: float = 0.8, sentiment: str = "bullish") -> AggregateAnalysis:
    return AggregateAnalysis(
        overall_sentiment=sentiment,
        overall_confidence=confidence,
        net_short_term_view=f"{sentiment} short-term signal",
        action_bias="watch",
        final_reason="test",
        provider="gemini",
    )


def test_signal_v1_strong_positive_news_is_bullish() -> None:
    signal = CompositeSignalEngine().compute(_quote(), [_article("bullish", 0.9, 0.9)], _aggregate(0.9, "bullish"))

    assert signal.composite_label == "bullish"
    assert signal.composite_score > 0.18
    assert signal.mode == "News + Quote Quality"


def test_signal_v1_strong_negative_news_is_bearish() -> None:
    signal = CompositeSignalEngine().compute(_quote(), [_article("bearish", 0.9, 0.9)], _aggregate(0.9, "bearish"))

    assert signal.composite_label == "bearish"
    assert signal.composite_score < -0.18


def test_signal_v1_neutral_news_stays_neutral() -> None:
    signal = CompositeSignalEngine().compute(_quote(), [_article("neutral", 0.8, 0.8)], _aggregate(0.8, "neutral"))

    assert signal.composite_label == "neutral"
    assert -0.18 <= signal.composite_score <= 0.18


def test_signal_v1_threshold_boundaries_are_strict() -> None:
    engine = CompositeSignalEngine()
    published_at = _now() - timedelta(minutes=10)
    bullish_edge = _article("bullish", 0.62, 1.0)
    bearish_edge = _article("bearish", 0.38, 1.0)
    bullish_edge[0].published_at = published_at
    bearish_edge[0].published_at = published_at
    just_over_bullish = _article("bullish", 0.63, 1.0)
    just_over_bearish = _article("bearish", 0.37, 1.0)
    just_over_bullish[0].published_at = published_at
    just_over_bearish[0].published_at = published_at

    exact_threshold = engine.compute(None, [bullish_edge, bearish_edge], _aggregate(0.5, "neutral"))
    above_threshold = engine.compute(None, [just_over_bullish, just_over_bearish], _aggregate(0.5, "bullish"))

    assert round(exact_threshold.composite_score, 6) == 0.18
    assert exact_threshold.composite_label == "neutral"
    assert above_threshold.composite_score > 0.18
    assert above_threshold.composite_label == "bullish"


def test_signal_v1_unavailable_quote_does_not_create_market_mode_or_penalty() -> None:
    unavailable = _quote(
        current_price=None,
        market_timestamp=None,
        spread_percentage=0.5,
        freshness_seconds=None,
        quality_status="unconfigured",
        provider_status=ProviderStatus.unconfigured("polygon", "market_quote", "missing key"),
    )
    signal = CompositeSignalEngine().compute(unavailable, [], _aggregate(0.0, "neutral"))

    assert signal.mode == "Unavailable"
    assert signal.composite_score == 0.0
    assert signal.signal_confidence == 0.0


def test_signal_v1_stale_quote_applies_freshness_penalty_without_positive_market_component() -> None:
    stale = _quote(
        quality_status="stale",
        freshness_seconds=2100,
        provider_status=ProviderStatus.stale_status("polygon", "market_quote", "previous close"),
    )

    signal = CompositeSignalEngine().compute(stale, [_article("bullish", 0.8, 0.8)], _aggregate(0.8, "bullish"))

    assert signal.mode == "News + Quote Quality"
    assert signal.composite_score < 0.75
    assert signal.signal_confidence < 0.8


def test_signal_v1_liquidity_spread_penalty_reduces_score() -> None:
    tight = CompositeSignalEngine().compute(_quote(spread_percentage=0.0), [_article("bullish", 0.8, 0.8)], _aggregate(0.8))
    wide = CompositeSignalEngine().compute(_quote(spread_percentage=0.02), [_article("bullish", 0.8, 0.8)], _aggregate(0.8))

    assert wide.composite_score < tight.composite_score


def test_signal_v1_confidence_comes_from_aggregate_not_direction_probability() -> None:
    signal = CompositeSignalEngine().compute(_quote(), [_article("bullish", 0.95, 0.9)], _aggregate(0.42, "bullish"))

    assert signal.signal_confidence == 0.42


def test_signal_v1_is_deterministic_for_same_inputs() -> None:
    quote = _quote()
    pair = _article("bullish", 0.8, 0.7)
    aggregate = _aggregate(0.8, "bullish")
    engine = CompositeSignalEngine()

    first = engine.compute(quote, [pair], aggregate)
    second = engine.compute(quote, [pair], aggregate)

    assert first == second
