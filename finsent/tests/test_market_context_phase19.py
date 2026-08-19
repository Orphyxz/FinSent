from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd

from finsent.app.dashboard.pages import compare, stock_detail, summary
from finsent.app.dashboard.view_model import (
    build_compare_frame,
    build_compare_market_context_table,
    build_compare_relative_chart,
    build_market_context_panel,
    build_overview_market_context,
    build_relative_performance_chart,
)
from finsent.app.services.catalyst_intelligence import CatalystArticleInput, CatalystIntelligenceService
from finsent.app.services.intelligence_service import IntelligenceService
from finsent.app.services.llm_analyzers import ArticleAnalysis
from finsent.app.services.market_context import (
    MarketContextService,
    MarketRegime,
    RelativeStrengthLabel,
    aligned_returns,
    classify_market_regime,
    classify_relative_strength,
    classify_volatility,
    historical_beta,
    realized_volatility,
    relative_return,
    return_correlation,
    sector_etf_for_symbol,
    window_return,
)
from finsent.app.services.market_providers import QuoteSnapshot
from finsent.app.services.news_providers import NormalizedNewsArticle
from finsent.app.services.signal_engine import CompositeSignalEngine
from finsent.app.services.signal_service_v2 import SignalEngineV2Service
from finsent.app.services.symbol_registry import registry


def test_return_and_relative_return_calculations_cover_positive_negative_flat_and_missing() -> None:
    assert round(window_return(_bars([100, 102.5])) or 0.0, 4) == 0.025
    assert round(window_return(_bars([100, 98])) or 0.0, 4) == -0.02
    assert window_return(_bars([100, 100])) == 0.0
    assert window_return(_bars([100])) is None
    assert round(relative_return(0.025, 0.006) or 0.0, 4) == 0.019
    assert relative_return(None, 0.006) is None


def test_relative_strength_thresholds_are_transparent() -> None:
    assert classify_relative_strength(0.02) == RelativeStrengthLabel.STRONG_RELATIVE_STRENGTH
    assert classify_relative_strength(0.008) == RelativeStrengthLabel.RELATIVE_STRENGTH
    assert classify_relative_strength(0.001) == RelativeStrengthLabel.IN_LINE
    assert classify_relative_strength(-0.008) == RelativeStrengthLabel.RELATIVE_WEAKNESS
    assert classify_relative_strength(-0.02) == RelativeStrengthLabel.STRONG_RELATIVE_WEAKNESS
    assert classify_relative_strength(None) == RelativeStrengthLabel.UNKNOWN


def test_correlation_uses_aligned_returns_not_price_levels() -> None:
    stock = _bars([100, 102, 101, 103, 102])
    market = _bars([50, 51, 50.5, 51.5, 51])
    inverse = _bars([50, 49, 49.5, 48.5, 49])
    shifted = _bars([50, 51, 51.5, 52, 52.5], start_minute=30)

    assert return_correlation(stock, market) is not None
    assert (return_correlation(stock, inverse) or 0.0) < 0
    assert return_correlation(stock, shifted) is None
    assert aligned_returns(stock, market).shape[0] == 4


def test_beta_handles_normal_high_low_zero_variance_and_insufficient() -> None:
    market = _bars([100, 101, 100, 102, 101])
    high_beta = _bars([100, 103, 100, 106, 103])
    low_beta = _bars([100, 100.5, 100, 101, 100.5])
    flat_market = _bars([100, 100, 100, 100, 100])

    assert (historical_beta(high_beta, market) or 0.0) > 1.0
    assert 0.0 < (historical_beta(low_beta, market) or 0.0) < 1.0
    assert historical_beta(high_beta, flat_market) is None
    assert historical_beta(_bars([100, 101]), market) is None


def test_volatility_labels_flat_low_high_and_missing() -> None:
    flat_vol = realized_volatility(_bars([100, 100, 100, 100]))
    high_vol = realized_volatility(_bars([100, 110, 90, 115, 85]))

    assert flat_vol == 0.0
    assert high_vol and high_vol > 0.05
    assert classify_volatility(flat_vol, 0.01)[0].value == "LOW"
    assert classify_volatility(high_vol, 0.01)[0].value == "HIGH"
    assert classify_volatility(None, 0.01)[0].value == "UNKNOWN"


def test_market_regime_rules_are_deterministic() -> None:
    assert classify_market_regime(0.01, 0.015, 0.005) == MarketRegime.RISK_ON
    assert classify_market_regime(-0.01, -0.015, 0.005) == MarketRegime.RISK_OFF
    assert classify_market_regime(0.01, -0.004, 0.005) == MarketRegime.MIXED
    assert classify_market_regime(0.004, 0.004, 0.025) == MarketRegime.HIGH_VOLATILITY
    assert classify_market_regime(None, None, None) == MarketRegime.UNKNOWN


def test_sector_mapping_for_supported_us_demo_symbols() -> None:
    expected = {
        "AAPL": "XLK",
        "MSFT": "XLK",
        "NVDA": "XLK",
        "AMZN": "XLY",
        "TSLA": "XLY",
        "META": "XLC",
        "GOOGL": "XLC",
        "JPM": "XLF",
    }

    assert {symbol: sector_etf_for_symbol(symbol) for symbol in expected} == expected


def test_market_context_service_batches_and_caches_benchmark_fetches() -> None:
    router = FakeRouter(
        {
            "SPY": [100, 101, 102, 103],
            "QQQ": [100, 102, 103, 105],
            "XLK": [100, 101, 103, 104],
            "AAPL": [100, 103, 105, 106],
            "MSFT": [200, 202, 204, 206],
            "NVDA": [300, 306, 312, 318],
        }
    )
    service = MarketContextService(router=router, clock=lambda: datetime(2026, 8, 19, 16, 0), ttl_seconds=300)

    first = service.build_contexts(["AAPL", "MSFT", "NVDA"], price_df=_empty_price_frame())
    second = service.build_contexts(["AAPL", "MSFT", "NVDA"], price_df=_empty_price_frame())

    assert len(first) == 3
    assert len(second) == 3
    assert router.calls["SPY"] == 1
    assert router.calls["XLK"] == 1
    assert router.calls["QQQ"] == 1


def test_market_context_failure_isolation_for_missing_sector_and_non_us() -> None:
    router = FakeRouter({"SPY": [100, 101, 102, 103], "QQQ": [100, 101, 103, 104], "AAPL": [100, 101, 102, 103]})
    service = MarketContextService(router=router, clock=lambda: datetime(2026, 8, 19, 16, 0))

    aapl = service.build_contexts(["AAPL"], price_df=_empty_price_frame())[0]
    nse = service.build_contexts(["NSE:TCS"], price_df=_empty_price_frame())[0]

    assert aapl.quality.value in {"PARTIAL", "INSUFFICIENT"}
    assert "Sector benchmark unavailable." in aapl.warnings
    assert nse.quality.value == "UNAVAILABLE"
    assert "Benchmark context not configured for this market." in nse.warnings


def test_dashboard_market_context_components_and_compare_columns_render() -> None:
    market_context = pd.DataFrame(
        [
            {
                "symbol": "AAPL",
                "benchmark_symbol": "SPY",
                "sector_benchmark_symbol": "XLK",
                "stock_return": 0.03,
                "benchmark_return": 0.01,
                "sector_return": 0.015,
                "qqq_return": 0.012,
                "market_relative_return": 0.02,
                "sector_relative_return": 0.015,
                "relative_strength_label": "STRONG_RELATIVE_STRENGTH",
                "stock_volatility": 0.01,
                "benchmark_volatility": 0.006,
                "sector_volatility": 0.008,
                "volatility_ratio": 1.7,
                "volatility_label": "ELEVATED",
                "correlation_to_market": 0.8,
                "correlation_to_sector": 0.7,
                "correlation_label": "HIGH_POSITIVE",
                "beta_to_market": 1.2,
                "market_regime": "RISK_ON",
                "sector_regime": "BULLISH",
                "stock_move_context": "STOCK_SPECIFIC_STRENGTH",
                "quality": "GOOD",
                "freshness": "LIVE",
            }
        ]
    )
    compare_df = build_compare_frame(_news_frame(), _price_frame("AAPL"), pd.DataFrame(), catalyst_df=pd.DataFrame(), market_context_df=market_context)
    ids: set[str] = set()
    for layout_factory in [summary.layout, stock_detail.layout, compare.layout]:
        ids.update(_component_ids(layout_factory()))

    assert {"summary-market-context", "stock-market-context-panel", "stock-relative-chart", "compare-market-context-table"}.issubset(ids)
    assert {"market_relative_return", "sector_relative_return", "beta_to_market", "market_context_quality"}.issubset(compare_df.columns)
    assert build_market_context_panel(market_context, "AAPL")
    assert build_overview_market_context(market_context, compare_df)
    assert build_compare_market_context_table(compare_df)
    assert build_compare_relative_chart(compare_df).data


def test_relative_performance_chart_degrades_without_benchmark_bars() -> None:
    fig = build_relative_performance_chart("AAPL", _price_frame("AAPL"), pd.DataFrame())

    assert fig.layout.title.text == "Relative Performance"


def test_signal_v1_v2_values_remain_unchanged_by_market_context_service() -> None:
    symbol = registry.get("US", "AAPL")
    article = _article(symbol.ticker)
    analysis = ArticleAnalysis(True, "bullish", 0.8, 0.6, "intraday", "product", "FinBERT positive.", "finbert", "ok")
    quote = _quote(symbol.ticker)
    bars = _v2_bars()
    aggregate = IntelligenceService().llm.aggregate(symbol, [(article, analysis)])
    evaluation_timestamp = datetime(2026, 8, 19, 15, 5)

    before_v1 = CompositeSignalEngine().compute(quote, [(article, analysis)], aggregate)
    before_v2 = SignalEngineV2Service().evaluate(SignalEngineV2Service().build_input(instrument=symbol, news_pairs=[(article, analysis)], quote=quote, price_bars=bars, evaluation_timestamp=evaluation_timestamp)).result
    MarketContextService(router=FakeRouter({"SPY": [100, 101, 102], "QQQ": [100, 101, 102], "XLK": [100, 101, 102], "AAPL": [100, 103, 104]}), clock=lambda: evaluation_timestamp).build_contexts(["AAPL"], price_df=_empty_price_frame())
    after_v1 = CompositeSignalEngine().compute(quote, [(article, analysis)], aggregate)
    after_v2 = SignalEngineV2Service().evaluate(SignalEngineV2Service().build_input(instrument=symbol, news_pairs=[(article, analysis)], quote=quote, price_bars=bars, evaluation_timestamp=evaluation_timestamp)).result

    assert before_v1 == after_v1
    assert before_v2.final_score == after_v2.final_score
    assert before_v2.label == after_v2.label
    assert before_v2.confidence == after_v2.confidence


def test_phase18_catalyst_classifier_still_groups_events() -> None:
    service = CatalystIntelligenceService()
    results = service.analyze(
        [
            CatalystArticleInput("one", "NVDA", "Nvidia beats earnings estimates on record revenue", published_at=datetime(2026, 8, 19, 15, 0)),
            CatalystArticleInput("two", "NVDA", "Nvidia earnings results beat estimates as revenue reaches record high", published_at=datetime(2026, 8, 19, 15, 30)),
        ]
    )

    assert len({result.event_group_id for result in results}) == 1


@dataclass
class FakeResult:
    data: pd.DataFrame
    provider: str = "fake"
    leaf_provider: str = "fake"


class FakeRouter:
    def __init__(self, frames: dict[str, list[float]]) -> None:
        self.frames = frames
        self.calls: dict[str, int] = {}

    def fetch_price_bars(self, symbol, *, start, end, interval):
        del start, end, interval
        ticker = symbol.provider_symbol
        self.calls[ticker] = self.calls.get(ticker, 0) + 1
        values = self.frames.get(ticker)
        return FakeResult(_bars(values or []))


def _bars(values: list[float], start_minute: int = 0) -> pd.DataFrame:
    if not values:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    timestamps = pd.date_range("2026-08-19 14:30", periods=len(values), freq="15min") + pd.Timedelta(minutes=start_minute)
    return pd.DataFrame(
        {
            "Open": values,
            "High": [value + 0.5 for value in values],
            "Low": [max(value - 0.5, 0.01) for value in values],
            "Close": values,
            "Volume": [1000] * len(values),
        },
        index=timestamps,
    )


def _empty_price_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["ticker", "timestamp", "open", "high", "low", "close", "volume"])


def _price_frame(ticker: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"ticker": ticker, "timestamp": pd.Timestamp("2026-08-19 14:30"), "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1000},
            {"ticker": ticker, "timestamp": pd.Timestamp("2026-08-19 14:45"), "open": 101, "high": 103, "low": 100, "close": 103, "volume": 1400},
        ]
    )


def _news_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ticker": "AAPL",
                "published_at": pd.Timestamp("2026-08-19 15:00"),
                "sentiment_score": 0.7,
                "model_confidence": 0.8,
                "signal_confidence": 0.8,
                "sentiment_label": "bullish",
                "title": "Apple beats earnings estimates",
            }
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


def _v2_bars() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Open": 100, "High": 101, "Low": 99, "Close": 100, "Volume": 1000},
            {"Open": 101, "High": 103, "Low": 100, "Close": 102, "Volume": 1400},
            {"Open": 102, "High": 106, "Low": 102, "Close": 105, "Volume": 2200},
        ],
        index=pd.to_datetime(["2026-08-19 14:30", "2026-08-19 14:45", "2026-08-19 15:00"]),
    )
