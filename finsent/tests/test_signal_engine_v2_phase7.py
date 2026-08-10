from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from finsent.app.database import entities  # noqa: F401
from finsent.app.database.base import Base, apply_sqlite_migrations
from finsent.app.database.entities import SignalRun
from finsent.app.services.llm_analyzers import AggregateAnalysis, ArticleAnalysis
from finsent.app.services.market_providers import QuoteSnapshot
from finsent.app.services.news_providers import NormalizedNewsArticle
from finsent.app.services.provider_reliability import DataMode, DataQualityAssessment, DataQualityLabel, FreshnessLabel
from finsent.app.services.signal_engine import CompositeSignalEngine
from finsent.app.services.signal_engine_v2 import (
    ENGINE_NAME_V2,
    ENGINE_VERSION_V2,
    SignalEngineV2,
    SignalInputV2,
    SignalNewsItemV2,
    component_to_dict,
    confidence_label,
    score_label,
)
from finsent.app.services.signal_service_v2 import SignalEngineV2Service
from finsent.app.services.symbol_registry import registry


NOW = datetime(2026, 8, 9, 10, 0, 0)


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    apply_sqlite_migrations(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with Session() as db:
        yield db


def _symbol():
    symbol = registry.get("US", "AAPL")
    assert symbol is not None
    return symbol


def _article(title="Apple beats expectations", hours_old=1, relevance=1.0):
    return NormalizedNewsArticle(
        article_id=title,
        ticker="AAPL",
        exchange="US",
        source="Reuters",
        title=title,
        summary="Test summary",
        url=f"https://example.com/{abs(hash(title))}",
        published_at=NOW - timedelta(hours=hours_old),
        ingested_at=NOW,
        provider="polygon",
        dedupe_hash=f"hash-{abs(hash(title))}",
        relevance_score=relevance,
    )


def _analysis(sentiment="bullish", confidence=0.8, impact=0.7, relevant=True, parse_status="ok"):
    return ArticleAnalysis(
        relevant=relevant,
        sentiment=sentiment,
        confidence=confidence,
        impact_strength=impact,
        time_horizon="1-3d",
        catalyst_tag="earnings",
        short_reason="Test analysis.",
        provider="gemini",
        parse_status=parse_status,
    )


def _news_item(sentiment="bullish", confidence=0.8, impact=0.7, hours_old=1, relevance=1.0, relevant=True, parse_status="ok"):
    return SignalNewsItemV2(_article(hours_old=hours_old, relevance=relevance), _analysis(sentiment, confidence, impact, relevant, parse_status))


def _quote(freshness=30, spread=0.001, quality_status="live"):
    return QuoteSnapshot(
        symbol="AAPL",
        exchange="US",
        provider_symbol="AAPL",
        current_price=100.0,
        currency="USD",
        bid=99.95,
        ask=100.05,
        spread_absolute=0.1,
        spread_percentage=spread,
        volume=1_000_000.0,
        market_timestamp=NOW - timedelta(seconds=freshness),
        ingested_at=NOW,
        provider="polygon",
        freshness_seconds=freshness,
        quality_status=quality_status,
        note="test quote",
    )


def _bars(direction="up", volume="normal", count=20):
    closes = []
    base = 100.0
    for idx in range(count):
        if direction == "up":
            closes.append(base + idx * 0.4)
        elif direction == "down":
            closes.append(base - idx * 0.4)
        elif direction == "conflict":
            value = base + idx * 0.5
            if idx == count - 2:
                value -= 1.0
            elif idx == count - 1:
                value -= 4.0
            closes.append(value)
        else:
            closes.append(base)
    volumes = [1000.0 for _ in range(count)]
    if volume == "high":
        volumes[-1] = 3000.0
    elif volume == "low":
        volumes[-1] = 300.0
    elif volume == "missing":
        volumes = [float("nan") for _ in range(count)]
    frame = pd.DataFrame(
        {
            "timestamp": [NOW - timedelta(minutes=15 * (count - idx)) for idx in range(count)],
            "Open": closes,
            "High": [value + 1 for value in closes],
            "Low": [value - 1 for value in closes],
            "Close": closes,
            "Volume": volumes,
        }
    ).set_index("timestamp")
    return frame


def _quality(score=0.9, freshness=FreshnessLabel.FRESH, label=DataQualityLabel.HIGH):
    return DataQualityAssessment(score, label, [], freshness, "polygon", DataMode.LIVE, NOW)


def _input(news_items=None, bars=None, quote=None, quote_quality=None, bars_quality=None, news_quality=None):
    return SignalInputV2(
        instrument=_symbol(),
        evaluation_timestamp=NOW,
        news_items=news_items or [],
        quote=quote,
        price_bars=bars,
        quote_quality=quote_quality,
        bars_quality=bars_quality,
        news_quality=news_quality,
    )


def _component(result, name):
    return next(component for component in result.components if component.name == name)


def test_news_component_strong_bullish_and_bearish() -> None:
    engine = SignalEngineV2()

    bullish = engine.news_component(_input(news_items=[_news_item("bullish")]))
    bearish = engine.news_component(_input(news_items=[_news_item("bearish")]))

    assert bullish.normalized_value > 0
    assert bearish.normalized_value < 0


def test_news_component_neutral_low_relevance_low_confidence_old_and_heuristic() -> None:
    engine = SignalEngineV2()
    neutral = engine.news_component(_input(news_items=[_news_item("neutral", confidence=0.8, impact=0.7)]))
    low = engine.news_component(_input(news_items=[_news_item("bullish", confidence=0.1, impact=0.2, relevance=0.1)]))
    old = engine.news_component(_input(news_items=[_news_item("bullish", hours_old=96)]))
    heuristic = engine.news_component(_input(news_items=[_news_item("bullish", parse_status="heuristic_unconfigured")]))

    assert neutral.normalized_value == 0
    assert low.reliability < 0.2
    assert old.metadata["total_weight"] < engine.news_component(_input(news_items=[_news_item("bullish", hours_old=1)])).metadata["total_weight"]
    assert heuristic.metadata["total_weight"] < engine.news_component(_input(news_items=[_news_item("bullish")])).metadata["total_weight"]


def test_news_disagreement_reduces_confidence_not_direction_magic() -> None:
    engine = SignalEngineV2()
    conflict = engine.news_component(_input(news_items=[_news_item("bullish"), _news_item("bearish")]))
    aligned = engine.news_component(_input(news_items=[_news_item("bullish"), _news_item("bullish")]))

    assert abs(conflict.normalized_value) < abs(aligned.normalized_value)
    assert conflict.metadata["agreement"] < aligned.metadata["agreement"]


def test_no_news_component_is_unavailable() -> None:
    component = SignalEngineV2().news_component(_input())

    assert component.available is False
    assert component.normalized_value == 0


def test_momentum_up_down_flat_conflicting_and_insufficient() -> None:
    engine = SignalEngineV2()

    up = engine.momentum_component(_input(bars=_bars("up")))
    down = engine.momentum_component(_input(bars=_bars("down")))
    flat = engine.momentum_component(_input(bars=_bars("flat")))
    conflict = engine.momentum_component(_input(bars=_bars("conflict")))
    insufficient = engine.momentum_component(_input(bars=_bars("up", count=1)))

    assert up.normalized_value > 0
    assert down.normalized_value < 0
    assert flat.normalized_value == 0
    assert conflict.metadata["agreement"] < up.metadata["agreement"]
    assert insufficient.available is False


def test_momentum_extreme_return_is_bounded_and_deterministic() -> None:
    frame = _bars("up")
    frame.iloc[-1, frame.columns.get_loc("Close")] = 1000.0
    engine = SignalEngineV2()

    first = engine.momentum_component(_input(bars=frame))
    second = engine.momentum_component(_input(bars=frame.copy()))

    assert first.normalized_value <= 1.0
    assert first == second


def test_volume_confirms_existing_direction_but_not_flat_direction() -> None:
    engine = SignalEngineV2()
    news = engine.news_component(_input(news_items=[_news_item("bullish")]))
    up = engine.momentum_component(_input(bars=_bars("up", "high")))
    high = engine.volume_component(_input(bars=_bars("up", "high")), news, up)
    low = engine.volume_component(_input(bars=_bars("up", "low")), news, up)
    flat_momentum = engine.momentum_component(_input(bars=_bars("flat", "high")))
    flat_volume = engine.volume_component(_input(bars=_bars("flat", "high")), engine.news_component(_input()), flat_momentum)

    assert high.normalized_value > 0
    assert low.normalized_value < high.normalized_value
    assert flat_volume.normalized_value == 0


def test_volume_missing_and_invalid_baseline_unavailable() -> None:
    engine = SignalEngineV2()
    news = engine.news_component(_input(news_items=[_news_item("bullish")]))
    momentum = engine.momentum_component(_input(bars=_bars("up")))
    missing = engine.volume_component(_input(bars=_bars("up", "missing")), news, momentum)
    zero = _bars("up")
    zero["Volume"] = 0.0
    invalid = engine.volume_component(_input(bars=zero), news, momentum)

    assert missing.available is False
    assert invalid.available is False


def test_liquidity_freshness_and_quality_reduce_reliability_not_direction() -> None:
    engine = SignalEngineV2()
    base = _input(news_items=[_news_item("bullish")], bars=_bars("up"), quote=_quote(spread=0.001), quote_quality=_quality(), bars_quality=_quality(), news_quality=_quality())
    wide = _input(news_items=[_news_item("bullish")], bars=_bars("up"), quote=_quote(spread=0.05), quote_quality=_quality(0.3, FreshnessLabel.STALE, DataQualityLabel.LOW), bars_quality=_quality(0.3, FreshnessLabel.STALE, DataQualityLabel.LOW), news_quality=_quality(0.3, FreshnessLabel.STALE, DataQualityLabel.LOW))

    good_result = engine.evaluate(base)
    poor_result = engine.evaluate(wide)

    assert good_result.final_score > 0
    assert poor_result.final_score > 0
    assert poor_result.final_score < good_result.final_score
    assert _component(poor_result, "liquidity").reliability < _component(good_result, "liquidity").reliability


def test_missing_bid_ask_and_unknown_freshness_warn_without_inverting_direction() -> None:
    quote = _quote()
    quote.bid = None
    quote.ask = None
    quote.spread_percentage = None
    result = SignalEngineV2().evaluate(_input(news_items=[_news_item("bullish")], bars=_bars("up"), quote=quote))

    assert result.final_score > 0
    assert result.warnings


def test_final_engine_agreement_conflict_news_only_market_only_and_missing() -> None:
    engine = SignalEngineV2()
    agreement = engine.evaluate(_input(news_items=[_news_item("bullish")], bars=_bars("up", "high"), quote=_quote()))
    conflict = engine.evaluate(_input(news_items=[_news_item("bullish")], bars=_bars("down", "high"), quote=_quote()))
    news_only = engine.evaluate(_input(news_items=[_news_item("bearish")]))
    market_only = engine.evaluate(_input(bars=_bars("up"), quote=_quote()))
    missing = engine.evaluate(_input())

    assert agreement.label in {"bullish", "strong_bullish"}
    assert conflict.confidence < agreement.confidence
    assert news_only.signal_mode == "NEWS_ONLY"
    assert market_only.signal_mode == "MARKET_ONLY"
    assert missing.signal_mode == "INSUFFICIENT_DATA"
    assert missing.confidence == 0


def test_score_confidence_bounds_thresholds_and_labels() -> None:
    assert score_label(0.55) == "strong_bullish"
    assert score_label(0.20) == "bullish"
    assert score_label(-0.20) == "bearish"
    assert score_label(0.0) == "neutral"
    assert confidence_label(0.70) == "high"
    assert confidence_label(0.40) == "medium"
    result = SignalEngineV2().evaluate(_input(news_items=[_news_item("bullish")], bars=_bars("up")))
    assert -1 <= result.final_score <= 1
    assert 0 <= result.confidence <= 1


def test_explanation_factors_and_no_trading_language() -> None:
    result = SignalEngineV2().evaluate(_input(news_items=[_news_item("bullish")], bars=_bars("down"), quote=_quote(spread=0.05)))
    text = result.explanation.lower()

    assert result.top_supporting_factors or result.top_opposing_factors
    assert "buy now" not in text
    assert "sell" not in text


def test_component_serialization_shape() -> None:
    component = SignalEngineV2().news_component(_input(news_items=[_news_item("bullish")]))
    payload = component_to_dict(component)

    assert payload["name"] == "news"
    assert "normalized_value" in payload
    assert "metadata" in payload


def test_v1_numerical_behavior_remains_identical() -> None:
    quote = _quote()
    article = _article()
    analysis = _analysis()
    aggregate = AggregateAnalysis("bullish", 0.8, "bullish short-term signal", "buy", "test", "gemini")
    engine = CompositeSignalEngine()

    before = engine.compute(quote, [(article, analysis)], aggregate)
    SignalEngineV2().evaluate(_input(news_items=[SignalNewsItemV2(article, analysis)], bars=_bars("up"), quote=quote))
    after = engine.compute(quote, [(article, analysis)], aggregate)

    assert before == after


def test_v2_does_not_mutate_input_objects() -> None:
    frame = _bars("up")
    original_columns = list(frame.columns)
    quote = _quote()

    SignalEngineV2().evaluate(_input(news_items=[_news_item("bullish")], bars=frame, quote=quote))

    assert list(frame.columns) == original_columns
    assert quote.current_price == 100.0


def test_v2_persists_distinct_engine_version_and_coexists(session) -> None:
    service = SignalEngineV2Service(session=session)
    signal_input = service.build_input(instrument=_symbol(), news_pairs=[(_article(), _analysis())], quote=_quote(), price_bars=_bars("up"), evaluation_timestamp=NOW)

    record = service.evaluate(signal_input, persist=True, experiment_id=7)
    session.commit()

    row = session.execute(select(SignalRun).where(SignalRun.id == record.persisted_run_id)).scalar_one()
    assert row.engine_name == ENGINE_NAME_V2
    assert row.engine_version == ENGINE_VERSION_V2
    assert row.experiment_id == 7
    assert row.future_component_json is not None


def test_service_requires_session_for_persistence() -> None:
    service = SignalEngineV2Service()
    signal_input = service.build_input(instrument=_symbol(), news_pairs=[(_article(), _analysis())])

    with pytest.raises(ValueError):
        service.evaluate(signal_input, persist=True)
