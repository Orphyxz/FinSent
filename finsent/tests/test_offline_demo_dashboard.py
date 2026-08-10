from __future__ import annotations

from sqlalchemy import func, select

from finsent.app.dashboard.view_model import (
    DATA_MODE_LOCAL,
    build_dashboard_state,
    detect_data_mode,
    get_default_compare_tickers,
    get_default_ticker_for_exchange,
    get_local_research_summary,
)
from finsent.app.database.base import SessionLocal
from finsent.app.database.entities import EventStudyResult, ExperimentRun, NewsArticle, SentimentAnalysisRun, SignalRun


def test_local_research_mode_detects_transferred_research_state() -> None:
    summary = get_local_research_summary()

    assert detect_data_mode() == DATA_MODE_LOCAL
    assert summary["articles"] >= 400
    assert summary["sentiment_runs"] >= 300
    assert summary["signal_runs"] >= 700
    assert summary["price_bars"] >= 1000
    assert summary["final_status"] == "COMPLETED_LOCKED"


def test_default_demo_symbol_and_peers_have_local_coverage() -> None:
    focus = get_default_ticker_for_exchange("US")
    peers = get_default_compare_tickers(focus, "US")

    assert focus in {"AMZN", "NVDA", "TSLA"}
    assert peers[:2]
    assert all(peer in {"AMZN", "NVDA", "TSLA", "AAPL", "GOOGL"} for peer in peers)


def test_dashboard_state_uses_stored_news_finbert_prices_and_research_signals() -> None:
    focus = get_default_ticker_for_exchange("US")
    state = build_dashboard_state(focus, get_default_compare_tickers(focus, "US"), "medium", None, None)

    assert state.data_mode == DATA_MODE_LOCAL
    assert not state.news_df.empty
    assert not state.price_df.empty
    assert not state.compare_df.empty
    assert set(state.compare_df["ticker"]).issuperset({focus})
    assert "finbert" in {str(value).lower() for value in state.news_df["analysis_provider"].dropna().unique()}
    assert state.compare_df["avg_confidence"].max() > 0
    assert "Historical research signal" in str(state.compare_df["mode"].iloc[0])
    assert state.signal_meta_map[focus]["research_signals"]["v1"]["engine_version"] == "1.0"
    assert "v2" in state.signal_meta_map[focus]["research_signals"]


def test_offline_demo_labels_missing_live_quote_without_hiding_historical_data() -> None:
    focus = get_default_ticker_for_exchange("US")
    state = build_dashboard_state(focus, get_default_compare_tickers(focus, "US"), "medium", None, None)
    row = state.compare_df[state.compare_df["ticker"] == focus].iloc[0]

    assert row["quote_provider"] == "unavailable"
    assert row["quote_quality"] == "unavailable"
    assert row["bars_status"] == "available"
    assert row["news_volume"] > 0
    assert row["last_close"] > 0


def test_dashboard_state_build_does_not_mutate_research_tables() -> None:
    entities = [NewsArticle, SentimentAnalysisRun, SignalRun, EventStudyResult, ExperimentRun]
    with SessionLocal() as session:
        before = _counts(session, entities)

    focus = get_default_ticker_for_exchange("US")
    build_dashboard_state(focus, get_default_compare_tickers(focus, "US"), "medium", None, None)

    with SessionLocal() as session:
        after = _counts(session, entities)

    assert after == before


def _counts(session, entities: list[type]) -> dict[str, int]:
    return {
        entity.__tablename__: session.execute(select(func.count()).select_from(entity)).scalar_one()
        for entity in entities
    }
