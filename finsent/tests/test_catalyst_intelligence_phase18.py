from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from finsent.app.dashboard.pages import compare, news_impact, stock_detail, summary
from finsent.app.dashboard.view_model import (
    build_active_catalysts,
    build_catalyst_frame,
    build_catalyst_summary,
    build_compare_catalyst_table,
    build_compare_frame,
    build_key_catalysts,
    build_news_table,
)
from finsent.app.services.catalyst_intelligence import (
    CatalystArticleInput,
    CatalystDirection,
    CatalystIntelligenceService,
    CatalystType,
    TimeHorizon,
)
from finsent.app.services.intelligence_service import IntelligenceService
from finsent.app.services.llm_analyzers import ArticleAnalysis
from finsent.app.services.market_providers import QuoteSnapshot
from finsent.app.services.news_providers import NormalizedNewsArticle
from finsent.app.services.signal_engine import CompositeSignalEngine
from finsent.app.services.signal_service_v2 import SignalEngineV2Service
from finsent.app.services.symbol_registry import registry


def test_catalyst_classifier_maps_core_taxonomy() -> None:
    service = CatalystIntelligenceService()
    cases = [
        ("Apple beats earnings estimates on stronger revenue", CatalystType.EARNINGS),
        ("Nvidia raises guidance after record AI chip demand", CatalystType.GUIDANCE),
        ("Tesla announces acquisition of charging software startup", CatalystType.M_AND_A),
        ("Meta faces antitrust investigation from regulators", CatalystType.REGULATION),
        ("Apple hit with patent lawsuit in federal court", CatalystType.LITIGATION),
        ("Nvidia unveils new AI platform for developers", CatalystType.PRODUCT),
        ("Amazon partners with Anthropic on cloud AI collaboration", CatalystType.PARTNERSHIP),
        ("Morgan Stanley upgrades Tesla and raises price target", CatalystType.ANALYST_RATING),
        ("Apple CFO steps down as company names successor", CatalystType.MANAGEMENT),
        ("Amazon announces layoffs and restructuring plan", CatalystType.LAYOFFS),
        ("Tesla plans convertible debt offering", CatalystType.FINANCING),
        ("Stocks move as Fed rate outlook shifts after CPI", CatalystType.MACRO),
    ]

    results = [service.classify(_input(title, index=index)) for index, (title, _expected) in enumerate(cases)]

    assert [result.catalyst_type for result in results] == [expected for _title, expected in cases]


def test_catalyst_direction_is_not_finbert_sentiment() -> None:
    service = CatalystIntelligenceService()
    result = service.classify(
        _input(
            "Tesla beats earnings estimates but cuts guidance for next quarter",
            sentiment_label="bullish",
        )
    )
    unknown = service.classify(_input("Apple shares trade mixed in quiet session", sentiment_label="bullish"))

    assert result.direction == CatalystDirection.MIXED
    assert unknown.direction == CatalystDirection.UNKNOWN


def test_catalyst_impact_horizon_grouping_and_novelty() -> None:
    service = CatalystIntelligenceService()
    first = _input("Nvidia beats earnings estimates on record revenue", article_id="one")
    repeat = _input(
        "Nvidia earnings results beat estimates as revenue reaches record high",
        article_id="two",
        published_at=datetime(2026, 8, 19, 15, 30),
    )
    analyst = _input("BofA downgrades Nvidia and cuts price target", article_id="three")

    results = service.analyze([first, repeat, analyst])
    earnings = [result for result in results if result.catalyst_type == CatalystType.EARNINGS]
    analyst_result = next(result for result in results if result.catalyst_type == CatalystType.ANALYST_RATING)

    assert {result.event_group_id for result in earnings} == {earnings[0].event_group_id}
    assert {result.novelty_label.value for result in earnings} == {"NEW", "REPEATED"}
    assert max(result.impact_score for result in earnings) >= 0.80
    assert analyst_result.direction == CatalystDirection.BEARISH
    assert analyst_result.time_horizon == TimeHorizon.SHORT_TERM
    assert analyst_result.event_group_id != earnings[0].event_group_id


def test_dashboard_catalyst_frame_and_news_table_fields() -> None:
    news_df = _news_frame()

    catalyst_df = build_catalyst_frame(news_df)
    enriched_news = news_df.merge(
        catalyst_df[["article_id", "catalyst_type", "catalyst_direction", "catalyst_impact_label", "catalyst_time_horizon", "event_group_id", "novelty_label"]],
        left_on=news_df["id"].astype(str),
        right_on="article_id",
        how="left",
    )
    table = build_news_table(pd.DataFrame(), enriched_news)

    assert not catalyst_df.empty
    assert {"catalyst_type", "catalyst_direction", "event_group_id", "novelty_label"}.issubset(catalyst_df.columns)
    assert {"Catalyst Direction", "Catalyst Impact", "Catalyst Horizon", "Event Group"}.issubset(table.columns)


def test_dashboard_catalyst_sections_render_without_live_providers() -> None:
    catalyst_df = build_catalyst_frame(_news_frame())
    compare_df = build_compare_frame(_news_frame(), _empty_price_frame(), pd.DataFrame(), catalyst_df=catalyst_df)

    assert build_active_catalysts(catalyst_df)
    assert build_catalyst_summary(catalyst_df, "AAPL")
    assert build_key_catalysts(catalyst_df, "AAPL")
    assert build_compare_catalyst_table(compare_df)
    for layout_factory in [summary.layout, stock_detail.layout, news_impact.layout, compare.layout]:
        assert layout_factory() is not None


def test_dashboard_layout_exposes_phase18_component_ids() -> None:
    ids: set[str] = set()
    for layout_factory in [summary.layout, stock_detail.layout, news_impact.layout, compare.layout]:
        ids.update(_component_ids(layout_factory()))

    assert {
        "summary-active-catalysts",
        "stock-catalyst-summary",
        "stock-key-catalysts",
        "stock-catalyst-timeline",
        "news-symbol-filter",
        "news-catalyst-filter",
        "news-direction-filter",
        "compare-catalyst-table",
    }.issubset(ids)


def test_signal_v1_v2_outputs_are_unchanged_by_catalyst_classification() -> None:
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
        index=pd.to_datetime(["2026-08-19 14:30", "2026-08-19 14:45", "2026-08-19 15:00"]),
    )
    service = IntelligenceService()
    aggregate = service.llm.aggregate(symbol, [(article, analysis)])
    evaluation_timestamp = datetime(2026, 8, 19, 15, 5)

    before_v1 = CompositeSignalEngine().compute(quote, [(article, analysis)], aggregate)
    before_v2 = SignalEngineV2Service().evaluate(
        SignalEngineV2Service().build_input(
            instrument=symbol,
            news_pairs=[(article, analysis)],
            quote=quote,
            price_bars=bars,
            evaluation_timestamp=evaluation_timestamp,
        )
    ).result
    CatalystIntelligenceService().classify(_input("Apple launches new product", article_id=article.article_id))
    after_v1 = CompositeSignalEngine().compute(quote, [(article, analysis)], aggregate)
    after_v2 = SignalEngineV2Service().evaluate(
        SignalEngineV2Service().build_input(
            instrument=symbol,
            news_pairs=[(article, analysis)],
            quote=quote,
            price_bars=bars,
            evaluation_timestamp=evaluation_timestamp,
        )
    ).result

    assert before_v1 == after_v1
    assert before_v2.final_score == after_v2.final_score
    assert before_v2.label == after_v2.label
    assert before_v2.confidence == after_v2.confidence


def _input(
    title: str,
    *,
    article_id: str | None = None,
    index: int = 0,
    sentiment_label: str = "neutral",
    published_at: datetime | None = None,
) -> CatalystArticleInput:
    return CatalystArticleInput(
        article_id=article_id or f"a{index}",
        primary_symbol="NVDA",
        title=title,
        summary="Current market headline",
        source="Benzinga",
        url=f"https://example.com/{article_id or index}",
        published_at=published_at or datetime(2026, 8, 19, 15, 0),
        sentiment_label=sentiment_label,
        sentiment_confidence=0.82,
        relevance_score=1.0,
    )


def _news_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "id": 101,
                "ticker": "AAPL",
                "exchange": "US",
                "provider": "alpaca",
                "source": "Benzinga",
                "title": "Apple beats earnings estimates and raises guidance",
                "summary": "Revenue beat expectations.",
                "url": "https://example.com/aapl",
                "published_at": pd.Timestamp("2026-08-19T15:00:00"),
                "dedupe_hash": "aapl-1",
                "relevance_score": 1.0,
                "sentiment_label": "bullish",
                "sentiment_score": 0.7,
                "model_confidence": 0.86,
                "signal_confidence": 0.86,
                "impact_strength": 0.6,
                "time_horizon": "intraday",
                "catalyst_tag": "earnings",
                "analysis_provider": "finbert",
                "parse_status": "ok",
                "short_reason": "Earnings and guidance are material for near-term expectations.",
            },
            {
                "id": 102,
                "ticker": "TSLA",
                "exchange": "US",
                "provider": "alpaca",
                "source": "Reuters",
                "title": "Tesla shares trade mixed in quiet session",
                "summary": "No major company-specific catalyst.",
                "url": "https://example.com/tsla",
                "published_at": pd.Timestamp("2026-08-19T14:00:00"),
                "dedupe_hash": "tsla-1",
                "relevance_score": 0.7,
                "sentiment_label": "neutral",
                "sentiment_score": 0.0,
                "model_confidence": 0.6,
                "signal_confidence": 0.6,
                "impact_strength": 0.2,
                "time_horizon": "intraday",
                "catalyst_tag": "unknown",
                "analysis_provider": "finbert",
                "parse_status": "ok",
                "short_reason": "",
            },
        ]
    )


def _component_ids(component) -> set[str]:
    ids: set[str] = set()
    component_id = getattr(component, "id", None)
    if component_id:
        ids.add(component_id)
    children = getattr(component, "children", None)
    if children is None:
        return ids
    if isinstance(children, (list, tuple)):
        for child in children:
            ids.update(_component_ids(child))
    else:
        ids.update(_component_ids(children))
    return ids


def _empty_price_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["ticker", "timestamp", "open", "high", "low", "close", "volume"])


def _article(ticker: str) -> NormalizedNewsArticle:
    return NormalizedNewsArticle(
        article_id="a1",
        ticker=ticker,
        exchange="US",
        source="Benzinga",
        title=f"{ticker} launches new product",
        summary="Current market headline",
        url="https://example.com/a1",
        published_at=datetime(2026, 8, 19, 15, 0),
        ingested_at=datetime(2026, 8, 19, 15, 1),
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
        market_timestamp=datetime(2026, 8, 19, 15, 0, tzinfo=timezone.utc).replace(tzinfo=None),
        ingested_at=datetime(2026, 8, 19, 15, 0),
        provider="alpaca",
        freshness_seconds=10,
        quality_status="live",
        note="Alpaca snapshot feed=iex; LIVE; market_status=MARKET OPEN",
        feed="iex",
        market_status="MARKET OPEN",
        freshness_label="LIVE",
    )
