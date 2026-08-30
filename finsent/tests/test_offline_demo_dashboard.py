from __future__ import annotations

import pytest
from sqlalchemy import func, select

from finsent.app.config.settings import settings
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


def test_local_research_mode_detects_transferred_research_state(monkeypatch) -> None:
    _disable_live_credentials(monkeypatch)
    summary = get_local_research_summary()
    _require_full_data_bundle(summary)

    assert detect_data_mode() == DATA_MODE_LOCAL
    assert summary["articles"] >= 400
    assert summary["sentiment_runs"] >= 300
    assert summary["signal_runs"] >= 700
    assert summary["price_bars"] >= 1000
    assert summary["final_status"] == "COMPLETED_LOCKED"


def test_default_demo_symbol_and_peers_are_live_watchlist_first(monkeypatch) -> None:
    _disable_live_credentials(monkeypatch)
    focus = get_default_ticker_for_exchange("US")
    peers = get_default_compare_tickers(focus, "US")

    assert focus == "AAPL"
    assert peers == ["NVDA", "TSLA"]


def test_dashboard_state_uses_stored_news_finbert_prices_and_research_signals(monkeypatch) -> None:
    _disable_live_credentials(monkeypatch)
    _require_full_data_bundle(get_local_research_summary())
    focus = "AMZN"
    state = build_dashboard_state(focus, ["NVDA", "TSLA"], "medium", None, None)

    assert state.data_mode == DATA_MODE_LOCAL
    assert not state.news_df.empty
    assert not state.price_df.empty
    assert not state.compare_df.empty
    assert set(state.compare_df["ticker"]).issuperset({focus})
    assert {"finbert", "imported_stored_sentiment"} & {str(value).lower() for value in state.news_df["analysis_provider"].dropna().unique()}
    assert state.compare_df["avg_confidence"].max() > 0
    assert set(state.compare_df["mode"].astype(str)).issubset({"News + Quote Quality", "Historical research signal (Signal V1)"})
    assert state.signal_meta_map[focus]["research_signals"]["v1"]["engine_version"] == "1.0"
    assert "v2" in state.signal_meta_map[focus]["research_signals"]


def test_offline_demo_labels_missing_live_quote_without_hiding_historical_data(monkeypatch) -> None:
    _disable_live_credentials(monkeypatch)
    focus = get_default_ticker_for_exchange("US")
    state = build_dashboard_state(focus, get_default_compare_tickers(focus, "US"), "medium", None, None)
    row = state.compare_df[state.compare_df["ticker"] == focus].iloc[0]

    assert row["quote_provider"] in {"unavailable", "alpaca"}
    assert row["quote_quality"] in {"unavailable", "live", "delayed", "stale"}
    assert row["bars_status"] == "available"
    assert row["news_volume"] > 0
    assert row["last_close"] > 0


def test_dashboard_state_build_does_not_mutate_research_tables(monkeypatch) -> None:
    _disable_live_credentials(monkeypatch)
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


def _require_full_data_bundle(summary: dict[str, object]) -> None:
    if int(summary.get("articles", 0)) < 400:
        pytest.skip("optional FinSent research data bundle is not installed")


def _disable_live_credentials(monkeypatch) -> None:
    for name in [
        "ALPACA_API_KEY",
        "ALPACA_API_SECRET",
        "POLYGON_API_KEY",
        "MARKETAUX_API_TOKEN",
        "KITE_API_KEY",
        "KITE_ACCESS_TOKEN",
        "GEMINI_API_KEY",
    ]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(settings, "alpaca_api_key", "")
    monkeypatch.setattr(settings, "alpaca_api_secret", "")
    monkeypatch.setattr(settings, "polygon_api_key", "")
    monkeypatch.setattr(settings, "marketaux_api_token", "")
    monkeypatch.setattr(settings, "kite_api_key", "")
    monkeypatch.setattr(settings, "kite_access_token", "")
    monkeypatch.setattr(settings, "gemini_api_key", "")
