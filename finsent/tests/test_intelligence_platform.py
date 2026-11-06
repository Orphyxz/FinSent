from __future__ import annotations

import numpy as np
import pandas as pd

from finsent.app.analysis.technicals import macd, normalize_ohlcv, period_return, rsi, sma, technical_snapshot
from finsent.app.dashboard import charts
from finsent.app.dashboard.intelligence import mood_from_score, watchlist_for_market
from finsent.app.dashboard.pages import compare, news_impact, research, stock_detail, summary
from finsent.app.services.entity_extraction import extract_entities
from finsent.app.services.event_explorer import _summarize
from finsent.app.services.market_overview import summarize_history


def _bars(closes: list[float]) -> pd.DataFrame:
    dates = pd.bdate_range("2026-01-01", periods=len(closes))
    close = pd.Series(closes, dtype=float)
    return pd.DataFrame({"timestamp": dates, "Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close, "Volume": 1_000_000})


def _ids(component) -> set[str]:
    ids = {component.id} if getattr(component, "id", None) and isinstance(component.id, str) else set()
    children = getattr(component, "children", None)
    for child in children if isinstance(children, (list, tuple)) else [children]:
        if child is not None and not isinstance(child, (str, int, float)):
            ids |= _ids(child)
    return ids


def test_normalize_ohlcv_lowercases_sorts_and_dedupes() -> None:
    frame = _bars([3, 2, 1]).iloc[::-1]
    frame = pd.concat([frame, frame.tail(1)])
    normalized = normalize_ohlcv(frame)
    assert list(normalized.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert normalized["timestamp"].is_monotonic_increasing
    assert len(normalized) == 3


def test_rsi_is_bounded_and_saturates_on_one_way_moves() -> None:
    rising = pd.Series(np.arange(1, 60, dtype=float))
    falling = rising[::-1].reset_index(drop=True)
    assert rsi(rising).dropna().iloc[-1] == 100.0
    assert rsi(falling).dropna().iloc[-1] < 1.0
    noisy = pd.Series(100 + np.sin(np.arange(200)) * 5)
    values = rsi(noisy).dropna()
    assert ((values >= 0) & (values <= 100)).all()


def test_macd_histogram_is_line_minus_signal() -> None:
    close = pd.Series(100 + np.cumsum(np.random.default_rng(7).normal(0, 1, 120)))
    frame = macd(close)
    clean = frame.dropna()
    assert np.allclose(clean["histogram"], clean["macd"] - clean["signal"])


def test_sma_and_period_return() -> None:
    close = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0])
    assert sma(close, 5).iloc[-1] == 12.0
    assert abs(period_return(close, 4) - 0.4) < 1e-12
    assert period_return(close, 10) is None


def test_technical_snapshot_classifies_a_steady_uptrend() -> None:
    snapshot = technical_snapshot(_bars(list(np.linspace(100, 200, 260))))
    assert snapshot.trend == "Uptrend"
    assert snapshot.rsi_zone == "Overbought"
    assert snapshot.high_52w is not None and snapshot.low_52w is not None
    assert snapshot.return_1y is not None and snapshot.return_1y > 0


def test_technical_snapshot_handles_empty_history() -> None:
    snapshot = technical_snapshot(pd.DataFrame())
    assert snapshot.bars == 0
    assert snapshot.rsi_zone == "Insufficient data"
    assert snapshot.trend == "Insufficient data"


def test_entity_extraction_finds_companies_people_and_regulators() -> None:
    entities = extract_entities("Nvidia CEO Jensen Huang says Microsoft demand is strong as the SEC reviews chip exports")
    assert "NVIDIA" in entities.companies and "Microsoft" in entities.companies
    assert entities.people == ("Jensen Huang",)
    assert "SEC" in entities.organizations


def test_entity_extraction_avoids_common_headline_false_positives() -> None:
    entities = extract_entities("Bernstein Raises Apple Price Target to $380 as Big Tech rallies on U.S. Dollar weakness")
    assert entities.companies == ("Apple",)
    title_case = extract_entities("SPCX CEO Elon Musk Fires Back at Regulators")
    assert title_case.people == ("Elon Musk",)
    assert extract_entities("Tesla Faces Risk, Bitunix Analyst Says").people == ()


def test_sparkline_is_a_data_uri_and_needs_two_points() -> None:
    assert charts.sparkline_svg([1.0]) == ""
    uri = charts.sparkline_svg([1.0, 2.0, 1.5])
    assert uri.startswith("data:image/svg+xml;utf8,")


def test_summarize_history_reports_change_and_sparkline() -> None:
    result = summarize_history(_bars([100, 102, 101, 105]).rename(columns=str.lower), key="X", label="X", region="US", note="", currency="USD", points=3)
    assert result.last == 105
    assert round(result.change_pct, 6) == round(105 / 101 - 1, 6)
    assert len(result.sparkline) == 3


def test_mood_thresholds_and_watchlists() -> None:
    assert mood_from_score(None) == "No data"
    assert mood_from_score(0.2) == "Bullish"
    assert mood_from_score(-0.2) == "Bearish"
    assert mood_from_score(0.05) == "Neutral"
    assert "RELIANCE" in watchlist_for_market("INDIA")
    assert len(watchlist_for_market("ALL")) == 10


def test_event_summary_groups_by_direction_with_confidence_intervals() -> None:
    events = pd.DataFrame(
        {
            "v1_direction": ["BULLISH", "BULLISH", "BEARISH"],
            "ar_1D": [0.01, 0.03, -0.02],
            "ar_3D": [0.02, 0.04, None],
            "ar_5D": [None, None, None],
        }
    )
    summary_frame = _summarize(events)
    bullish_1d = summary_frame[(summary_frame["group"] == "BULLISH") & (summary_frame["window"] == "1D")].iloc[0]
    assert round(bullish_1d["mean"], 6) == 0.02 and bullish_1d["n"] == 2 and bullish_1d["ci"] > 0
    assert summary_frame[(summary_frame["group"] == "BEARISH") & (summary_frame["window"] == "1D")]["ci"].iloc[0] == 0.0
    assert "5D" not in set(summary_frame["window"])


def test_contribution_chart_colors_by_sign() -> None:
    figure = charts.contribution_chart([{"name": "news", "contribution": 0.05}, {"name": "price_momentum", "contribution": -0.03}])
    colors = figure.data[0].marker.color
    assert colors[0] == charts.COLORS["bull"] and colors[1] == charts.COLORS["bear"]


def test_intelligence_modules_expose_their_components() -> None:
    assert {"exec-indices", "exec-mood", "exec-watchlist", "exec-positive", "exec-negative", "exec-events", "watchlist-editor"} <= _ids(summary.layout())
    assert {"stock-main-chart", "stock-period", "stock-technicals", "stock-signal-compare", "stock-contrib-chart", "stock-signal-weights"} <= _ids(stock_detail.layout())
    assert {"news-feed", "news-donut", "news-intel-summary", "news-sentiment-filter"} <= _ids(news_impact.layout())
    assert {"compare-cards", "compare-perf-chart", "compare-catalyst-chart", "compare-volatility-chart"} <= _ids(compare.layout())
    assert {"research-event-table", "research-event-chart", "research-window"} <= _ids(research.layout())


def test_sector_breadth_and_treemap_from_quotes() -> None:
    from finsent.app.services.market_map import sector_breadth

    frame = pd.DataFrame(
        {
            "ticker": ["A", "B", "C", "D"],
            "name": ["A Co", "B Co", "C Co", "D Co"],
            "sector": ["Technology", "Technology", "Energy", "Energy"],
            "market": ["US"] * 4,
            "price": [10.0, 20.0, 30.0, 40.0],
            "change_pct": [0.02, -0.01, 0.03, None],
            "dollar_volume": [1e6, 2e6, None, None],
        }
    )
    breadth = sector_breadth(frame).set_index("sector")
    assert breadth.loc["Technology", "advancers"] == 1 and breadth.loc["Technology", "decliners"] == 1
    assert breadth.loc["Energy", "stocks"] == 1
    figure = charts.market_treemap(frame, size_by="liquidity")
    treemap = figure.data[0]
    assert set(treemap.parents) == {"", "Technology", "Energy"}
    assert len(treemap.ids) == 2 + 3


def test_benchmark_excess_return_aligns_on_common_days() -> None:
    from finsent.app.services.benchmarks import _aligned_returns, _excess

    days = pd.bdate_range("2026-01-01", periods=30)
    stock = pd.DataFrame({"timestamp": days, "close": np.linspace(100, 130, 30)})
    bench = pd.DataFrame({"timestamp": days, "close": np.linspace(100, 110, 30)})
    excess = _excess(stock, bench, 21)
    assert excess is not None and excess > 0
    returns = _aligned_returns(stock, bench.iloc[::2])
    assert len(returns) == 14


def test_scheduler_runs_due_jobs_once_and_respects_interval() -> None:
    import time as _time

    from finsent.app.services.scheduler import BackgroundScheduler

    calls: list[int] = []
    scheduler = BackgroundScheduler()
    scheduler.add("job", 3600, lambda: calls.append(1))
    scheduler.add("later", 3600, lambda: calls.append(2), initial_delay_seconds=3600)
    scheduler.run_pending()
    for _ in range(50):
        if calls:
            break
        _time.sleep(0.01)
    scheduler.run_pending()
    _time.sleep(0.05)
    assert calls == [1]
    assert scheduler.jobs[0].runs == 1


def test_sentiment_explanation_ranks_drivers() -> None:
    from finsent.app.services.sentiment_explainer import SentimentExplanation, WordWeight

    explanation = SentimentExplanation(
        "Bank downgrades Apple", -0.7, "bearish",
        (WordWeight("Bank", 0.02), WordWeight("downgrades", -0.69), WordWeight("Apple", -0.2)),
        True,
    )
    assert [w.word for w in explanation.top(positive=False)] == ["downgrades", "Apple"]
    assert [w.word for w in explanation.top(positive=True)] == ["Bank"]


def test_custom_watchlist_is_capped_per_market() -> None:
    from finsent.app.dashboard.intel_callbacks import MAX_WATCHLIST, _custom_watchlist

    tickers = [f"T{i}" for i in range(20)]
    assert _custom_watchlist({"US": tickers}, "US") == tickers[:MAX_WATCHLIST]
    assert _custom_watchlist({"US": tickers}, "INDIA") is None
    assert _custom_watchlist(None, "US") is None


def test_market_map_page_and_route() -> None:
    from finsent.app.dashboard.components import ANALYSIS_NAV_ITEMS
    from finsent.app.dashboard.pages import market_map

    assert {"market-treemap", "map-size", "map-gainers", "map-losers", "map-sector-breadth"} <= _ids(market_map.layout())
    assert ("Market Map", "/market-map") in ANALYSIS_NAV_ITEMS


def test_risk_stats_measure_drawdown_and_up_days() -> None:
    from finsent.app.analysis.technicals import risk_stats

    closes = [100.0] * 5 + [110.0, 120.0, 90.0, 95.0, 100.0] * 6
    stats = risk_stats(_bars(closes))
    assert round(stats.max_drawdown, 4) == round(90 / 120 - 1, 4)
    assert stats.worst_day < 0 < stats.best_day
    assert stats.annual_volatility > 0 and stats.sharpe is not None
    assert risk_stats(_bars([100.0, 101.0])).sharpe is None


def test_rolling_beta_recovers_a_known_multiple() -> None:
    from finsent.app.analysis.technicals import rolling_beta

    bench = pd.Series(np.random.default_rng(3).normal(0, 0.01, 120))
    beta = rolling_beta(bench * 1.5, bench, 60).dropna()
    assert len(beta) == 61 and np.allclose(beta, 1.5)


def test_correlation_heatmap_uses_common_days() -> None:
    days = pd.bdate_range("2026-01-01", periods=40)
    base = np.cumsum(np.random.default_rng(1).normal(0, 1, 40)) + 100
    series = {"A": pd.DataFrame({"timestamp": days, "close": base}), "B": pd.DataFrame({"timestamp": days, "close": base * 2})}
    figure = charts.correlation_heatmap(series)
    assert np.allclose(np.array(figure.data[0].z), 1.0)
    assert "Correlation needs" in charts.correlation_heatmap({"A": series["A"]}).layout.annotations[0].text


def test_plain_english_verdict_reads_news_and_momentum() -> None:
    from finsent.app.dashboard.widgets import stock_verdict

    aligned = stock_verdict("X", "Acme", "bullish", {"news": 0.4, "price_momentum": 0.3}, 0.05)
    assert "Recent news is positive and the price has been rising." in aligned[2].children
    assert "up 5.0%" in aligned[2].children
    mixed = stock_verdict("X", "Acme", "neutral", {"news": 0.4, "price_momentum": -0.3}, None)
    assert "while the price has been falling" in mixed[2].children


def test_simple_view_hides_analysis_sections() -> None:
    def classes_of(component, target):
        if getattr(component, "id", None) == target:
            return str(getattr(component, "className", ""))
        children = getattr(component, "children", None)
        for child in children if isinstance(children, (list, tuple)) else [children]:
            if child is not None and not isinstance(child, (str, int, float)):
                found = classes_of(child, target)
                if found is not None:
                    return found
        return None

    assert "analyst-only" in classes_of(summary.layout(), "summary-metric-row")
    assert "analyst-only" in classes_of(stock_detail.layout(), "stock-metric-row")
    assert "simple-only" in classes_of(summary.layout(), "exec-brief")
    assert "simple-only" in classes_of(stock_detail.layout(), "stock-verdict")
