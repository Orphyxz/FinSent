from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

import dash_bootstrap_components as dbc
import logging
import numpy as np
import pandas as pd
from dash import html
from plotly import graph_objects as go
from plotly.subplots import make_subplots
from sqlalchemy import func, select

from finsent.app.analysis.market_impact import align_news_with_prices, build_daily_impact_summary
from finsent.app.config.settings import settings
from finsent.app.database.base import SessionLocal, init_db
from finsent.app.database.entities import EventStudyResult, ExperimentRun, Instrument, NewsArticle, PriceBar, SentimentAnalysisRun, SignalRun
from finsent.app.database.repository import (
    NewsRepository,
    PriceRepository,
    QuoteSnapshotRepository,
    SignalSnapshotRepository,
)
from finsent.app.models.schemas import MarketSignalSnapshot
from finsent.app.services.intelligence_service import intelligence_service
from finsent.app.services.catalyst_intelligence import (
    CatalystDirection,
    CatalystType,
    build_catalyst_inputs_from_news_frame,
    catalyst_intelligence_service,
    catalyst_results_to_records,
)
from finsent.app.services.symbol_registry import SymbolRecord, registry
from finsent.app.utils.logging import safe_log_message

if TYPE_CHECKING:
    from finsent.app.services.pipeline import FinSentPipeline


EXCHANGE_OPTIONS = [
    {"label": "US Markets", "value": "US"},
    {"label": "NSE India", "value": "NSE"},
    {"label": "BSE India", "value": "BSE"},
]
HORIZON_DAYS = {"short": 3, "medium": 7, "long": 30}
DATA_MODE_LIVE = "LIVE DATA"
DATA_MODE_LOCAL = "LOCAL RESEARCH DATA"
DATA_MODE_MIXED = "MIXED"
DATA_MODE_UNAVAILABLE = "UNAVAILABLE"
LOCAL_DEMO_SYMBOLS = ["AMZN", "NVDA", "TSLA", "AAPL", "GOOGL"]
LIVE_WATCHLIST_SYMBOLS = ["AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA", "JPM"]
DEFAULT_COMPARE_SYMBOLS = ["NVDA", "TSLA"]
PALETTE = {
    "bg": "#07111f",
    "paper": "#0c1729",
    "ink": "#e8eefb",
    "muted": "#9aa8c7",
    "accent": "#2dd4bf",
    "accent_2": "#fb923c",
    "bull": "#34d399",
    "bear": "#f87171",
    "neutral": "#fbbf24",
    "line": "#60a5fa",
    "grid": "#22314e",
}

logger = logging.getLogger(__name__)

NEWS_COLUMNS = [
    "id",
    "ticker",
    "exchange",
    "source",
    "provider",
    "title",
    "summary",
    "url",
    "published_at",
    "ingested_at",
    "dedupe_hash",
    "relevance_score",
    "sentiment_label",
    "sentiment_score",
    "model_label",
    "model_confidence",
    "text_score",
    "signal_confidence",
    "positive_score",
    "negative_score",
    "neutral_score",
    "bid_ask_spread",
    "spread_pct",
    "volume_ratio",
    "buy_sell_ratio",
    "buy_pressure",
    "market_signal",
    "relevant",
    "impact_strength",
    "time_horizon",
    "catalyst_tag",
    "short_reason",
    "analysis_provider",
    "parse_status",
]
PRICE_COLUMNS = ["ticker", "timestamp", "open", "high", "low", "close", "volume"]
COMPARE_COLUMNS = [
    "ticker",
    "name",
    "sector",
    "exchange",
    "currency",
    "last_close",
    "pct_change",
    "news_volume",
    "avg_sentiment",
    "avg_confidence",
    "avg_impact_pct",
    "avg_spread_pct",
    "avg_volume_ratio",
    "avg_buy_sell_ratio",
    "avg_market_signal",
    "volume",
    "quote_provider",
    "quote_quality",
    "bars_status",
    "news_quality",
    "freshness_seconds",
    "freshness_label",
    "market_status",
    "feed",
    "mode",
    "signal_label",
    "signal_confidence",
    "v2_score",
    "v2_label",
    "v2_confidence",
    "final_reason",
    "catalyst_count",
    "top_catalyst",
    "top_catalyst_direction",
    "top_catalyst_impact",
    "top_catalyst_title",
]


@dataclass(slots=True)
class DashboardState:
    news_df: pd.DataFrame
    price_df: pd.DataFrame
    event_df: pd.DataFrame
    daily_summary_df: pd.DataFrame
    compare_df: pd.DataFrame
    sector_df: pd.DataFrame
    snapshot_map: dict[str, MarketSignalSnapshot]
    quote_meta_map: dict[str, dict[str, object]]
    signal_meta_map: dict[str, dict[str, object]]
    demo_mode: bool
    data_status: str
    data_mode: str = DATA_MODE_UNAVAILABLE
    local_summary: dict[str, object] | None = None
    catalyst_df: pd.DataFrame = field(default_factory=pd.DataFrame)


def get_pipeline() -> FinSentPipeline:
    from finsent.app.services.pipeline import FinSentPipeline

    return FinSentPipeline()


def get_exchange_options() -> list[dict[str, str]]:
    return EXCHANGE_OPTIONS


def _symbol_from_value(raw_value: str | None, exchange_hint: str | None = None) -> SymbolRecord | None:
    if not raw_value:
        return None
    symbol = registry.resolve_any(raw_value)
    if symbol is not None:
        return symbol
    if exchange_hint:
        return registry.get(exchange_hint, raw_value)
    return None


def _storage_ticker(symbol: SymbolRecord) -> str:
    return intelligence_service.storage_ticker(symbol)


def _symbol_key(symbol: SymbolRecord) -> str:
    return symbol.provider_symbol


def _format_sentiment_score(label: str | None, confidence: float | None) -> float:
    direction = 1.0 if label == "bullish" else -1.0 if label == "bearish" else 0.0
    return direction * float(confidence or 0.0)


def _normalize_news_sentiment(news_df: pd.DataFrame) -> pd.DataFrame:
    if news_df.empty:
        return news_df
    work = news_df.copy()
    if "sentiment_label" in work.columns:
        mapped_label = (
            work["sentiment_label"]
            .astype(str)
            .str.lower()
            .replace({"positive": "bullish", "negative": "bearish", "neutral": "neutral"})
        )
        work["sentiment_label"] = mapped_label
    if "sentiment_score" not in work.columns:
        work["sentiment_score"] = 0.0
    score_series = pd.to_numeric(work["sentiment_score"], errors="coerce").fillna(0.0)
    if (score_series.abs() < 1e-9).all() and "sentiment_label" in work.columns:
        confidence = pd.to_numeric(work.get("model_confidence"), errors="coerce").fillna(
            pd.to_numeric(work.get("signal_confidence"), errors="coerce").fillna(0.0)
        )
        work["sentiment_score"] = [
            _format_sentiment_score(label, conf) for label, conf in zip(work["sentiment_label"], confidence, strict=False)
        ]
    return work


def filter_symbols_for_exchange(exchange_filter: str | None = None) -> list[SymbolRecord]:
    exchange = (exchange_filter or "US").upper().strip()
    return registry.list_symbols(exchange)


def get_ticker_options(exchange_filter: str | None = None) -> list[dict[str, str]]:
    symbols = filter_symbols_for_exchange(exchange_filter)
    local_symbols = set(get_local_research_symbols(exchange_filter))
    ordered = sorted(
        symbols,
        key=lambda symbol: (
            0 if symbol.ticker in LIVE_WATCHLIST_SYMBOLS else 1,
            LIVE_WATCHLIST_SYMBOLS.index(symbol.ticker) if symbol.ticker in LIVE_WATCHLIST_SYMBOLS else len(LIVE_WATCHLIST_SYMBOLS),
            0 if symbol.provider_symbol in local_symbols or symbol.ticker in local_symbols else 1,
            symbol.provider_symbol,
        ),
    )
    return [{"label": symbol.ui_label, "value": symbol.provider_symbol} for symbol in ordered]


def get_default_ticker_for_exchange(exchange_filter: str | None = None) -> str:
    if (exchange_filter or "US").upper().strip() == "US":
        return settings.default_ticker if settings.default_ticker in LIVE_WATCHLIST_SYMBOLS else "AAPL"
    local = get_local_research_symbols(exchange_filter)
    if local:
        return local[0]
    symbols = filter_symbols_for_exchange(exchange_filter)
    return symbols[0].provider_symbol if symbols else "AAPL"


def get_default_compare_tickers(focus_ticker: str | None = None, exchange_filter: str | None = "US") -> list[str]:
    focus = (focus_ticker or "").upper().strip()
    if (exchange_filter or "US").upper().strip() == "US":
        return [symbol for symbol in DEFAULT_COMPARE_SYMBOLS if symbol != focus]
    return [symbol for symbol in get_local_research_symbols(exchange_filter) if symbol != focus][:4]


def get_exchange_for_ticker(ticker: str) -> str:
    symbol = _symbol_from_value(ticker)
    if symbol is not None:
        return symbol.exchange
    normalized = (ticker or "").upper().strip()
    if normalized.endswith(".NS"):
        return "NSE"
    if normalized.endswith(".BO"):
        return "BSE"
    if ":" in normalized:
        return normalized.split(":", maxsplit=1)[0]
    return "US"


def get_company_name(ticker: str) -> str:
    symbol = _symbol_from_value(ticker)
    if symbol is not None:
        return symbol.display_name
    return (ticker or "").upper()


def get_price_status_note(ticker: str, has_price: bool, quote_meta: dict[str, object] | None = None) -> str:
    if quote_meta:
        source = quote_meta.get("provider") or "market feed"
        freshness = quote_meta.get("freshness_seconds")
        quality = str(quote_meta.get("quality_status") or "unavailable")
        age_note = (
            f"Last market update {int(float(freshness))}s ago"
            if freshness is not None and pd.notna(freshness)
            else "Freshness unavailable"
        )
        if quality == "live":
            return f"Live quote from {source} • {age_note}"
        if quality == "delayed":
            market_status = str(quote_meta.get("market_status") or "UNKNOWN")
            return f"Latest available market data from {source} ({market_status}) • {age_note}"
        if quality == "stale":
            market_status = str(quote_meta.get("market_status") or "UNKNOWN")
            return f"Stale/latest available market data from {source} ({market_status}) • {age_note}"
        note = str(quote_meta.get("note") or "").strip()
        if quality == "unconfigured":
            return f"Quote provider unconfigured: {note or source}"
        return f"Quote unavailable from {source}: {note}" if note else f"Quote unavailable from {source}"
    if has_price:
        return "Latest stored market close"
    if detect_data_mode() == DATA_MODE_LOCAL:
        return "LIVE QUOTE UNAVAILABLE. Showing historical research data below."
    return f"No market quote is currently available for {get_exchange_for_ticker(ticker)}"


def _has_live_credentials() -> bool:
    return any(
        [
            os.getenv("POLYGON_API_KEY", "").strip(),
            os.getenv("MARKETAUX_API_TOKEN", "").strip(),
            os.getenv("KITE_API_KEY", "").strip() and os.getenv("KITE_ACCESS_TOKEN", "").strip(),
            os.getenv("GEMINI_API_KEY", "").strip(),
            os.getenv("ALPACA_API_KEY", "").strip() and os.getenv("ALPACA_API_SECRET", "").strip(),
            settings.polygon_api_key.strip(),
            settings.marketaux_api_token.strip(),
            settings.kite_api_key.strip() and settings.kite_access_token.strip(),
            settings.gemini_api_key.strip(),
            settings.alpaca_api_key.strip() and settings.alpaca_api_secret.strip(),
        ]
    )


def local_research_available() -> bool:
    init_db()
    try:
        with SessionLocal() as session:
            article_count = session.execute(select(func.count()).select_from(NewsArticle)).scalar_one()
            price_count = session.execute(select(func.count()).select_from(PriceBar)).scalar_one()
            signal_count = session.execute(select(func.count()).select_from(SignalRun)).scalar_one()
    except Exception:
        return False
    return bool(article_count or price_count or signal_count or Path("output/research/phase16/FINAL_EVALUATION_SUMMARY.json").exists())


def detect_data_mode() -> str:
    has_local = local_research_available()
    has_live = _has_live_credentials()
    if has_local and has_live:
        return DATA_MODE_MIXED
    if has_local:
        return DATA_MODE_LOCAL
    if has_live:
        return DATA_MODE_LIVE
    return DATA_MODE_UNAVAILABLE


def get_local_research_symbols(exchange_filter: str | None = None) -> list[str]:
    exchange = (exchange_filter or "US").upper().strip()
    init_db()
    try:
        with SessionLocal() as session:
            rows = session.execute(
                select(
                    Instrument.display_symbol,
                    func.count(func.distinct(NewsArticle.id)).label("articles"),
                    func.count(func.distinct(PriceBar.id)).label("prices"),
                    func.count(func.distinct(SignalRun.id)).label("signals"),
                )
                .select_from(Instrument)
                .outerjoin(NewsArticle, NewsArticle.instrument_id == Instrument.id)
                .outerjoin(PriceBar, PriceBar.instrument_id == Instrument.id)
                .outerjoin(SignalRun, SignalRun.instrument_id == Instrument.id)
                .where(Instrument.exchange == exchange)
                .group_by(Instrument.display_symbol)
            ).all()
    except Exception:
        return []
    scored = [
        (
            str(symbol).upper(),
            int(articles or 0) + int(prices or 0) + int(signals or 0),
        )
        for symbol, articles, prices, signals in rows
        if int(articles or 0) or int(prices or 0) or int(signals or 0)
    ]
    return [
        symbol
        for symbol, _score in sorted(
            scored,
            key=lambda item: (
                LOCAL_DEMO_SYMBOLS.index(item[0]) if item[0] in LOCAL_DEMO_SYMBOLS else len(LOCAL_DEMO_SYMBOLS),
                -item[1],
                item[0],
            ),
        )
    ]


def get_local_research_summary() -> dict[str, object]:
    init_db()
    summary: dict[str, object] = {
        "articles": 0,
        "sentiment_runs": 0,
        "signal_runs": 0,
        "experiment_runs": 0,
        "instruments": 0,
        "price_bars": 0,
        "event_study_results": 0,
        "symbols": [],
        "final_status": "unavailable",
    }
    try:
        with SessionLocal() as session:
            summary.update(
                {
                    "articles": session.execute(select(func.count()).select_from(NewsArticle)).scalar_one(),
                    "sentiment_runs": session.execute(select(func.count()).select_from(SentimentAnalysisRun)).scalar_one(),
                    "signal_runs": session.execute(select(func.count()).select_from(SignalRun)).scalar_one(),
                    "experiment_runs": session.execute(select(func.count()).select_from(ExperimentRun)).scalar_one(),
                    "instruments": session.execute(select(func.count()).select_from(Instrument)).scalar_one(),
                    "price_bars": session.execute(select(func.count()).select_from(PriceBar)).scalar_one(),
                    "event_study_results": session.execute(select(func.count()).select_from(EventStudyResult)).scalar_one(),
                    "symbols": get_local_research_symbols("US"),
                }
            )
    except Exception:
        return summary
    final_summary = Path("output/research/phase16/FINAL_EVALUATION_SUMMARY.json")
    if final_summary.exists():
        summary["final_status"] = "COMPLETED_LOCKED"
    return summary


def format_age_from_timestamp(value: object) -> str:
    if value is None or (isinstance(value, float) and not pd.notna(value)):
        return "n/a"
    try:
        ts = pd.to_datetime(value, errors="coerce")
    except Exception:
        return "n/a"
    if pd.isna(ts):
        return "n/a"
    now = pd.Timestamp.utcnow().tz_localize(None)
    delta_seconds = max(int((now - ts.tz_localize(None) if getattr(ts, "tzinfo", None) is not None else now - ts).total_seconds()), 0)
    if delta_seconds < 60:
        return f"{delta_seconds}s"
    if delta_seconds < 3600:
        return f"{delta_seconds // 60}m"
    if delta_seconds < 86400:
        return f"{delta_seconds // 3600}h"
    return f"{delta_seconds // 86400}d"


def latest_recent_close(price_df: pd.DataFrame, max_age_minutes: int | None = None) -> float | None:
    if price_df.empty or "timestamp" not in price_df.columns or "close" not in price_df.columns:
        return None
    timestamps = pd.to_datetime(price_df["timestamp"], errors="coerce")
    if timestamps.dropna().empty:
        return None
    latest_idx = timestamps.idxmax()
    latest_ts = timestamps.loc[latest_idx]
    cutoff_minutes = max_age_minutes if max_age_minutes is not None else settings.live_price_max_age_minutes
    age = pd.Timestamp.utcnow().tz_localize(None) - latest_ts
    if age > pd.Timedelta(minutes=cutoff_minutes):
        return None
    try:
        value = float(price_df.loc[latest_idx, "close"])
    except (TypeError, ValueError):
        return None
    return value if pd.notna(value) else None


def _derive_news_quality(news_df: pd.DataFrame) -> str:
    if news_df.empty:
        return "unavailable"
    providers = {str(provider).strip().lower() for provider in news_df.get("provider", pd.Series(dtype=str)).dropna().tolist()}
    parse_statuses = {str(status).strip().lower() for status in news_df.get("parse_status", pd.Series(dtype=str)).dropna().tolist()}
    if any(status != "ok" for status in parse_statuses):
        return "inferred"
    if providers and providers.issubset({"polygon", "marketaux"}):
        return "provider-grade"
    if providers:
        return "fallback-quality"
    return "unavailable"


def _derive_bars_status(focus_ticker: str, price_df: pd.DataFrame, quote_meta: dict[str, object]) -> str:
    ticker_prices = price_df[price_df["ticker"] == focus_ticker] if not price_df.empty else pd.DataFrame()
    if not ticker_prices.empty:
        return "available"
    quality = str(quote_meta.get("quality_status") or "unavailable")
    if quality in {"live", "delayed", "stale"}:
        return "unavailable"
    return "unavailable"


def _is_usable_quote_meta(quote_meta: dict[str, object] | None) -> bool:
    if not quote_meta:
        return False
    try:
        current_price = float(quote_meta.get("current_price")) if quote_meta.get("current_price") is not None else None
    except (TypeError, ValueError):
        return False
    if current_price is None or current_price <= 0:
        return False
    if quote_meta.get("market_timestamp") is None:
        return False
    return str(quote_meta.get("quality_status") or "").strip().lower() in {"live", "delayed", "stale"}


def _quote_mode_label(quote_meta: dict[str, object]) -> str:
    note = str(quote_meta.get("note") or "").lower()
    quality = str(quote_meta.get("quality_status") or "unavailable").lower()
    if "previous-close" in note or "previous close" in note:
        return "previous_close"
    if "last trade" in note:
        return "last_trade"
    if "snapshot" in note:
        return "snapshot"
    if quality in {"live", "delayed", "stale", "unconfigured", "unavailable"}:
        return quality
    return "unknown"


def _data_quality_label(quote_meta: dict[str, object], news_quality: str, bars_status: str) -> str:
    usable_quote = _is_usable_quote_meta(quote_meta)
    quote_mode = _quote_mode_label(quote_meta)
    if usable_quote and quote_mode == "snapshot" and news_quality == "provider-grade" and bars_status == "available":
        return "HIGH"
    if usable_quote and news_quality in {"provider-grade", "fallback-quality"}:
        return "MEDIUM"
    if usable_quote or news_quality not in {"unavailable"}:
        return "LOW"
    return "UNAVAILABLE"


def build_focus_status_banner(focus_ticker: str, state: DashboardState) -> html.Div:
    local_summary = state.local_summary or {}
    compare_row = state.compare_df[state.compare_df["ticker"] == focus_ticker]
    ticker_news = state.news_df[state.news_df["ticker"] == focus_ticker].copy()
    quote_meta = state.quote_meta_map.get(focus_ticker, {})
    signal_meta = state.signal_meta_map.get(focus_ticker, {})

    price_source = str(quote_meta.get("provider") or "unavailable")
    price_quality = str(quote_meta.get("quality_status") or "unavailable")
    news_providers = sorted({str(value) for value in ticker_news.get("provider", pd.Series(dtype=str)).dropna().unique().tolist()})
    news_sources = sorted({str(value) for value in ticker_news.get("source", pd.Series(dtype=str)).dropna().unique().tolist()})
    news_provider_label = ", ".join(news_providers[:2]) if news_providers else "unavailable"
    news_source_label = ", ".join(news_sources[:2]) if news_sources else "unavailable"
    latest_news_at = ticker_news["published_at"].max() if not ticker_news.empty else None
    latest_quote_at = quote_meta.get("market_timestamp") or quote_meta.get("ingested_at")
    freshness_age = format_age_from_timestamp(latest_news_at or latest_quote_at)
    mode = str(signal_meta.get("mode") or compare_row["mode"].iloc[0] if not compare_row.empty else "Unavailable")
    news_quality = _derive_news_quality(ticker_news)
    bars_status = _derive_bars_status(focus_ticker, state.price_df, quote_meta)
    quote_mode = _quote_mode_label(quote_meta)
    data_quality = _data_quality_label(quote_meta, news_quality, bars_status)
    if mode == "News + Quote Quality" and price_quality == "live" and news_quality == "provider-grade":
        overall_quality = "live"
    elif mode == "Unavailable":
        overall_quality = "unavailable"
    elif mode == "Quote-quality fallback" and price_quality in {"live", "delayed", "stale"}:
        overall_quality = "inferred"
    elif news_quality in {"fallback-quality", "unavailable", "inferred"}:
        overall_quality = news_quality
    else:
        overall_quality = price_quality

    pills = [
        html.Div(f"Data mode: {state.data_mode}", className="status-pill"),
        html.Div(f"SQLite DB: {int(local_summary.get('articles', 0))} articles", className="status-pill"),
        html.Div(f"FinBERT: {int(local_summary.get('sentiment_runs', 0))} runs", className="status-pill"),
        html.Div(f"Research signals: {int(local_summary.get('signal_runs', 0))} runs", className="status-pill"),
        html.Div(f"Phase 16: {local_summary.get('final_status', 'unavailable')}", className="status-pill"),
        html.Div(f"Price source: {price_source}", className="status-pill"),
        html.Div(f"Quote mode: {quote_mode}", className="status-pill"),
        html.Div(f"Bars status: {bars_status}", className="status-pill"),
        html.Div(f"News provider: {news_provider_label}", className="status-pill"),
        html.Div(f"News tier: {news_quality}", className="status-pill"),
        html.Div(f"News source: {news_source_label}", className="status-pill"),
        html.Div(f"Freshness age: {freshness_age}", className="status-pill"),
        html.Div(f"Mode: {mode}", className="status-pill"),
        html.Div(f"Quality: {overall_quality}", className="status-pill"),
        html.Div(f"Data quality: {data_quality}", className="status-pill"),
    ]
    return html.Div(
        [
            html.Div("Runtime Status", className="status-value"),
            html.Div(state.data_status, className="status-copy"),
            html.Div(pills, className="badge-row"),
        ],
        className="status-banner",
    )


def normalize_tickers(raw_tickers: list[str | None]) -> list[str]:
    values: list[str] = []
    for ticker in raw_tickers:
        if not ticker:
            continue
        normalized = ticker.upper().strip()
        if normalized and normalized not in values:
            values.append(normalized)
    return values


def empty_news_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=NEWS_COLUMNS)


def empty_price_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=PRICE_COLUMNS)


def confidence_series(news_df: pd.DataFrame) -> pd.Series:
    if "signal_confidence" in news_df.columns:
        signal_confidence = pd.to_numeric(news_df["signal_confidence"], errors="coerce")
        model_confidence = pd.to_numeric(news_df.get("model_confidence"), errors="coerce")
        return signal_confidence.where(signal_confidence > 0).combine_first(model_confidence).fillna(0.0)
    if "model_confidence" in news_df.columns:
        return pd.to_numeric(news_df["model_confidence"], errors="coerce").fillna(0.0)
    if {"positive_score", "negative_score", "neutral_score"}.issubset(news_df.columns):
        return news_df[["positive_score", "negative_score", "neutral_score"]].max(axis=1).fillna(0.0)
    return pd.Series(0.0, index=news_df.index, dtype=float)


def spread_pct_series(news_df: pd.DataFrame) -> pd.Series:
    if "spread_pct" in news_df.columns:
        return pd.to_numeric(news_df["spread_pct"], errors="coerce").fillna(0.0)
    return pd.Series(0.0, index=news_df.index, dtype=float)


def volume_ratio_series(news_df: pd.DataFrame) -> pd.Series:
    if "volume_ratio" in news_df.columns:
        return pd.to_numeric(news_df["volume_ratio"], errors="coerce").fillna(1.0)
    return pd.Series(1.0, index=news_df.index, dtype=float)


def buy_sell_ratio_series(news_df: pd.DataFrame) -> pd.Series:
    if "buy_sell_ratio" in news_df.columns:
        return pd.to_numeric(news_df["buy_sell_ratio"], errors="coerce").fillna(1.0)
    return pd.Series(1.0, index=news_df.index, dtype=float)


def market_signal_series(news_df: pd.DataFrame) -> pd.Series:
    if "market_signal" in news_df.columns:
        return pd.to_numeric(news_df["market_signal"], errors="coerce").fillna(0.0)
    return pd.Series(0.0, index=news_df.index, dtype=float)


def label_for_signal(score: float) -> str:
    if score > 0.15:
        return "positive"
    if score < -0.15:
        return "negative"
    return "neutral"


def filter_to_fresh_news(news_df: pd.DataFrame) -> pd.DataFrame:
    if news_df.empty:
        return news_df
    work = news_df.copy()
    work["published_at"] = pd.to_datetime(work["published_at"], errors="coerce")
    cutoff = pd.Timestamp.utcnow().tz_localize(None) - pd.Timedelta(minutes=settings.live_news_max_age_minutes)
    fresh = work[work["published_at"] >= cutoff].copy()
    return fresh if not fresh.empty else empty_news_frame()


def expand_sparse_news_window(
    all_news_df: pd.DataFrame,
    filtered_news_df: pd.DataFrame,
    tickers: list[str],
    horizon: str,
    minimum_rows: int = 5,
    maximum_rows: int = 10,
) -> pd.DataFrame:
    if all_news_df.empty:
        return filtered_news_df

    work = all_news_df.copy()
    work["published_at"] = pd.to_datetime(work["published_at"], errors="coerce")
    work = work.dropna(subset=["published_at"])
    if work.empty:
        return filtered_news_df

    result = filtered_news_df.copy()
    anchor = work["published_at"].max()
    fallback_days = max(HORIZON_DAYS.get(horizon, 7), 4)
    recent_pool = work[work["published_at"] >= anchor - pd.Timedelta(days=fallback_days)].copy()

    for ticker in tickers:
        current_rows = result[result["ticker"] == ticker].copy()
        if len(current_rows) >= minimum_rows:
            continue

        ticker_pool = recent_pool[recent_pool["ticker"] == ticker].sort_values("published_at", ascending=False).copy()
        if ticker_pool.empty:
            continue

        existing_hashes = set(current_rows.get("dedupe_hash", pd.Series(dtype=str)).dropna().astype(str).tolist())
        supplement = ticker_pool[
            ~ticker_pool.get("dedupe_hash", pd.Series(dtype=str)).astype(str).isin(existing_hashes)
        ].head(max(maximum_rows - len(current_rows), 0))

        if not supplement.empty:
            result = supplement.copy() if result.empty else pd.concat([result, supplement], ignore_index=True)

    if result.empty:
        return result
    return (
        result.sort_values("published_at", ascending=True)
        .drop_duplicates(subset=["ticker", "dedupe_hash"], keep="last")
        .reset_index(drop=True)
    )


def needs_live_refresh(ticker: str, max_age_minutes: int | None = None) -> bool:
    symbol = _symbol_from_value(ticker)
    if symbol is None:
        return True
    max_age_seconds = float((max_age_minutes or settings.live_refresh_max_age_minutes) * 60)
    init_db()
    with SessionLocal() as session:
        quote_row = QuoteSnapshotRepository(session).latest_for_symbol(symbol.ticker, symbol.exchange)
        news_df = NewsRepository(session).list_news_df(symbol.ticker, symbol.exchange)
        price_df = PriceRepository(session).list_price_df(_storage_ticker(symbol))
    if quote_row is None:
        return True
    if quote_row.freshness_seconds is None or float(quote_row.freshness_seconds) > max_age_seconds:
        return True
    if price_df.empty:
        return True
    latest_bar = pd.to_datetime(price_df["timestamp"], errors="coerce").dropna()
    if latest_bar.empty:
        return True
    if (pd.Timestamp.utcnow().tz_localize(None) - latest_bar.max()) > pd.Timedelta(minutes=settings.live_price_max_age_minutes):
        return True
    if news_df.empty:
        return True
    latest_news = pd.to_datetime(news_df["published_at"], errors="coerce").dropna()
    if latest_news.empty:
        return True
    return (pd.Timestamp.utcnow().tz_localize(None) - latest_news.max()) > pd.Timedelta(minutes=max_age_minutes or settings.live_refresh_max_age_minutes)


def ensure_live_data(
    tickers: list[str],
    force: bool = False,
    limit: int | None = None,
) -> None:
    if not force and detect_data_mode() == DATA_MODE_LOCAL:
        return
    for ticker in normalize_tickers(tickers):
        symbol = _symbol_from_value(ticker)
        if symbol is None:
            continue
        if not force and not needs_live_refresh(symbol.provider_symbol):
            continue
        try:
            intelligence_service.run(symbol, news_limit=limit)
        except Exception as exc:
            logger.warning(
                "Live data refresh failed for %s (%s): %s",
                symbol.provider_symbol,
                type(exc).__name__,
                safe_log_message(exc),
            )
            continue


def load_live_data(
    tickers: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, dict[str, object]], dict[str, dict[str, object]]]:
    init_db()
    news_frames: list[pd.DataFrame] = []
    price_frames: list[pd.DataFrame] = []
    quote_meta_map: dict[str, dict[str, object]] = {}
    signal_meta_map: dict[str, dict[str, object]] = {}

    with SessionLocal() as session:
        news_repo = NewsRepository(session)
        price_repo = PriceRepository(session)
        quote_repo = QuoteSnapshotRepository(session)
        signal_repo = SignalSnapshotRepository(session)

        for ticker in tickers:
            symbol = _symbol_from_value(ticker)
            if symbol is None:
                continue
            key = _symbol_key(symbol)

            news_df = news_repo.list_news_df(ticker=symbol.ticker, exchange=symbol.exchange)
            if not news_df.empty:
                news_df = _merge_latest_sentiment_runs(session, news_df)
                news_df = _normalize_news_sentiment(news_df)
                news_df["ticker"] = key
                news_df["exchange"] = symbol.exchange
                news_frames.append(news_df)

            price_df = price_repo.list_price_df(_storage_ticker(symbol))
            if not price_df.empty:
                price_df["ticker"] = key
                price_frames.append(price_df)

            quote_row = quote_repo.latest_for_symbol(symbol.ticker, symbol.exchange)
            if quote_row is not None:
                note_meta = _parse_provider_note(quote_row.note)
                quote_meta_map[key] = {
                    "provider": quote_row.provider,
                    "current_price": quote_row.current_price,
                    "currency": quote_row.currency,
                    "bid": quote_row.bid,
                    "ask": quote_row.ask,
                    "spread_absolute": quote_row.spread_absolute,
                    "spread_percentage": quote_row.spread_percentage,
                    "volume": quote_row.volume,
                    "market_timestamp": quote_row.market_timestamp,
                    "ingested_at": quote_row.ingested_at,
                    "freshness_seconds": quote_row.freshness_seconds,
                    "quality_status": quote_row.quality_status,
                    "note": quote_row.note,
                    "market_status": note_meta.get("market_status") or ("UNKNOWN" if quote_row.provider == "unavailable" else "LATEST AVAILABLE"),
                    "feed": note_meta.get("feed"),
                    "freshness_label": "LIVE" if quote_row.quality_status == "live" else "LATEST AVAILABLE" if quote_row.quality_status in {"delayed", "stale"} else "UNKNOWN",
                    "usable_market_data": (
                        quote_row.current_price is not None
                        and quote_row.current_price > 0
                        and quote_row.market_timestamp is not None
                        and quote_row.quality_status in {"live", "delayed", "stale"}
                    ),
                }

            signal_row = signal_repo.latest_for_symbol(symbol.ticker, symbol.exchange)
            if signal_row is not None:
                signal_meta_map[key] = {
                    "composite_score": signal_row.composite_score,
                    "composite_label": signal_row.composite_label,
                    "signal_confidence": signal_row.signal_confidence,
                    "mode": signal_row.mode,
                    "overall_sentiment": signal_row.overall_sentiment,
                    "overall_confidence": signal_row.overall_confidence,
                    "action_bias": signal_row.action_bias,
                    "net_short_term_view": signal_row.net_short_term_view,
                    "final_reason": signal_row.final_reason,
                    "explanation_bullets": (signal_row.explanation_bullets or "").splitlines(),
                    "analysis_provider": signal_row.analysis_provider,
                    "quote_provider": signal_row.quote_provider,
                    "ingested_at": signal_row.ingested_at,
                }
            research_signal_meta = _latest_research_signal_meta(session, symbol)
            if research_signal_meta:
                existing_meta = signal_meta_map.get(key, {})
                merged = {**research_signal_meta, **existing_meta}
                merged_lines = [
                    *[str(line) for line in existing_meta.get("explanation_bullets", []) if line],
                    *[str(line) for line in research_signal_meta.get("explanation_bullets", []) if line],
                ]
                if merged_lines:
                    merged["explanation_bullets"] = list(dict.fromkeys(merged_lines))
                signal_meta_map[key] = merged

    news_df = pd.concat(news_frames, ignore_index=True) if news_frames else empty_news_frame()
    price_df = pd.concat(price_frames, ignore_index=True) if price_frames else empty_price_frame()

    if not news_df.empty:
        news_df["published_at"] = pd.to_datetime(news_df["published_at"], errors="coerce")
    if not price_df.empty:
        price_df["timestamp"] = pd.to_datetime(price_df["timestamp"], errors="coerce")
    return news_df, price_df, quote_meta_map, signal_meta_map


def _merge_latest_sentiment_runs(session, news_df: pd.DataFrame) -> pd.DataFrame:
    if news_df.empty or "id" not in news_df.columns:
        return news_df
    article_ids = [int(value) for value in news_df["id"].dropna().tolist()]
    if not article_ids:
        return news_df
    rows = session.execute(
        select(SentimentAnalysisRun)
        .where(SentimentAnalysisRun.article_id.in_(article_ids))
        .order_by(SentimentAnalysisRun.created_at.desc(), SentimentAnalysisRun.id.desc())
    ).scalars().all()
    latest_by_article: dict[int, SentimentAnalysisRun] = {}
    for row in rows:
        latest_by_article.setdefault(int(row.article_id), row)
    if not latest_by_article:
        return news_df
    work = news_df.copy()
    for idx, row in work.iterrows():
        article_id = row.get("id")
        if pd.isna(article_id):
            continue
        sentiment = latest_by_article.get(int(article_id))
        if sentiment is None:
            continue
        label = str(sentiment.sentiment_label or "").strip().lower()
        current_confidence = float(row.get("model_confidence") or 0.0)
        if current_confidence <= 0:
            work.at[idx, "sentiment_label"] = label or row.get("sentiment_label")
            work.at[idx, "model_label"] = label or row.get("model_label")
            work.at[idx, "model_confidence"] = sentiment.confidence
            work.at[idx, "signal_confidence"] = sentiment.confidence
            work.at[idx, "sentiment_score"] = sentiment.sentiment_score
            work.at[idx, "analysis_provider"] = sentiment.model_family or sentiment.provider or "finbert"
            work.at[idx, "parse_status"] = sentiment.parse_status or "ok"
            work.at[idx, "short_reason"] = sentiment.short_reason or row.get("short_reason")
            work.at[idx, "impact_strength"] = sentiment.impact_strength
            work.at[idx, "time_horizon"] = sentiment.time_horizon
            work.at[idx, "catalyst_tag"] = sentiment.catalyst_tag
    return work


def _parse_provider_note(note: str | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for part in str(note or "").split(";"):
        text = part.strip()
        if "feed=" in text:
            result["feed"] = text.split("feed=", maxsplit=1)[1].split()[0].strip()
        if "market_status=" in text:
            result["market_status"] = text.split("market_status=", maxsplit=1)[1].strip()
        elif "=" in text:
            key, value = text.split("=", maxsplit=1)
            result[key.strip().lower()] = value.strip()
    return result


def _latest_research_signal_meta(session, symbol: SymbolRecord) -> dict[str, object]:
    instrument = session.execute(
        select(Instrument).where(
            Instrument.display_symbol == symbol.ticker,
            Instrument.exchange == symbol.exchange,
        )
    ).scalar_one_or_none()
    if instrument is None:
        return {}
    rows = session.execute(
        select(SignalRun)
        .where(SignalRun.instrument_id == instrument.id)
        .order_by(SignalRun.generated_at.desc(), SignalRun.id.desc())
    ).scalars().all()
    if not rows:
        return {}
    live_meta: dict[str, object] = {}
    live_rows = [row for row in rows if _signal_provider_metadata(row).get("run_type") == "APPLICATION_LIVE_RUN"]
    if live_rows:
        latest_v2 = live_rows[0]
        live_components = _parse_signal_components(latest_v2)
        live_meta = {
            "live_v2": _signal_row_payload(latest_v2),
            "live_v2_components": live_components,
            "v2_component_lines": _v2_component_lines(live_components),
            "explanation_bullets": [
                f"LIVE SIGNAL V2: label {(latest_v2.label or 'neutral').upper()}, score {float(latest_v2.final_score or 0.0):+.3f}, confidence {float(latest_v2.confidence or 0.0):.3f}.",
                latest_v2.explanation or "Live Signal V2 was computed from current news, market momentum, volume, reliability, and freshness where available.",
                *_v2_component_lines(live_components),
            ],
        }
    by_version: dict[str, SignalRun] = {}
    research_rows = [row for row in rows if _signal_provider_metadata(row).get("run_type") != "APPLICATION_LIVE_RUN"]
    for row in research_rows:
        version = str(row.engine_version or row.engine_name or "").lower()
        if version == "1.0" or "v1" in str(row.engine_name or "").lower():
            by_version.setdefault("v1", row)
        elif "2.1" in version:
            by_version.setdefault("v2_1", row)
        elif "2.0" in version or "composite" in str(row.engine_name or "").lower():
            by_version.setdefault("v2", row)
    if not by_version:
        return live_meta
    active = by_version.get("v1") or research_rows[0]
    components = _parse_signal_components(by_version.get("v2"))
    research_lines = _research_signal_lines(active, by_version.get("v2"), by_version.get("v2_1"), components)
    live_lines = [str(line) for line in live_meta.get("explanation_bullets", []) if line]
    return {
        "composite_score": active.final_score,
        "composite_label": active.label,
        "signal_confidence": active.confidence,
        "mode": "Historical research signal (Signal V1)",
        "overall_sentiment": active.label,
        "overall_confidence": active.confidence,
        "action_bias": active.label,
        "net_short_term_view": "Historical research signal, not a live recommendation.",
        "final_reason": active.explanation or "Stored historical Signal V1 research row.",
        "explanation_bullets": [*live_lines, *research_lines],
        "analysis_provider": "stored_research_db",
        "quote_provider": "historical_research",
        "ingested_at": active.generated_at,
        "research_signals": {
            key: _signal_row_payload(value)
            for key, value in by_version.items()
            if value is not None
        },
        "v2_components": components,
        **{key: value for key, value in live_meta.items() if key != "explanation_bullets"},
    }


def _signal_provider_metadata(row: SignalRun) -> dict[str, object]:
    if not row.provider_metadata_json:
        return {}
    try:
        payload = json.loads(row.provider_metadata_json)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _signal_row_payload(row: SignalRun) -> dict[str, object]:
    return {
        "engine_name": row.engine_name,
        "engine_version": row.engine_version,
        "generated_at": row.generated_at,
        "score": row.final_score,
        "label": row.label,
        "confidence": row.confidence,
        "signal_mode": row.signal_mode,
        "news_component": row.news_component,
        "market_component": row.market_component,
        "explanation": row.explanation,
    }


def _parse_signal_components(row: SignalRun | None) -> list[dict[str, object]]:
    if row is None or not row.future_component_json:
        return []
    try:
        payload = json.loads(row.future_component_json)
    except json.JSONDecodeError:
        return []
    components = payload.get("components") if isinstance(payload, dict) else None
    if not isinstance(components, list):
        return []
    result: list[dict[str, object]] = []
    for component in components:
        if not isinstance(component, dict):
            continue
        result.append(
            {
                "name": component.get("name"),
                "normalized_value": component.get("normalized_value"),
                "contribution": component.get("contribution"),
                "reliability": component.get("reliability"),
                "available": component.get("available"),
                "reason": component.get("reason"),
            }
        )
    return result


def _research_signal_lines(active: SignalRun, v2: SignalRun | None, v21: SignalRun | None, components: list[dict[str, object]]) -> list[str]:
    lines = [
        f"HISTORICAL RESEARCH SIGNAL: Signal V1 {active.engine_version} generated {active.generated_at:%Y-%m-%d} with label {(active.label or 'neutral').upper()}, score {float(active.final_score or 0.0):+.3f}, confidence {float(active.confidence or 0.0):.3f}.",
    ]
    if v2 is not None:
        lines.append(
            f"RESEARCH V2.0: label {(v2.label or 'neutral').upper()}, score {float(v2.final_score or 0.0):+.3f}, confidence {float(v2.confidence or 0.0):.3f}; not promoted to live/default."
        )
    if v21 is not None:
        lines.append(
            f"V2.1 is an UNPROMOTED RESEARCH CANDIDATE: label {(v21.label or 'neutral').upper()}, score {float(v21.final_score or 0.0):+.3f}, confidence {float(v21.confidence or 0.0):.3f}."
        )
    for component in components[:3]:
        name = str(component.get("name") or "component").replace("_", " ").title()
        value = component.get("normalized_value")
        reliability = component.get("reliability")
        value_text = "n/a" if value is None else f"{float(value):+.3f}"
        reliability_text = "n/a" if reliability is None else f"{float(reliability):.3f}"
        lines.append(f"V2 component - {name}: value {value_text}, reliability {reliability_text}.")
    return lines


def _v2_component_lines(components: list[dict[str, object]]) -> list[str]:
    lines: list[str] = []
    for component in components:
        name = str(component.get("name") or "component").replace("_", " ").upper()
        if name in {"PRICE MOMENTUM"}:
            name = "MOMENTUM"
        if name in {"VOLUME CONFIRMATION"}:
            name = "VOLUME"
        if name not in {"NEWS", "MOMENTUM", "VOLUME", "FRESHNESS", "DATA QUALITY", "LIQUIDITY"}:
            continue
        available = "available" if component.get("available") else "missing"
        value = component.get("normalized_value")
        reliability = component.get("reliability")
        value_text = "n/a" if value is None else f"{float(value):+.3f}"
        reliability_text = "n/a" if reliability is None else f"{float(reliability):.3f}"
        lines.append(f"{name}: {available}; value {value_text}; reliability {reliability_text}.")
    return lines


def build_snapshot_map(
    tickers: list[str],
    quote_meta_map: dict[str, dict[str, object]],
    signal_meta_map: dict[str, dict[str, object]],
) -> dict[str, MarketSignalSnapshot]:
    snapshots: dict[str, MarketSignalSnapshot] = {}
    for ticker in tickers:
        quote_meta = quote_meta_map.get(ticker, {})
        signal_meta = signal_meta_map.get(ticker, {})
        bid = quote_meta.get("bid")
        ask = quote_meta.get("ask")
        spread_absolute = quote_meta.get("spread_absolute")
        snapshots[ticker] = MarketSignalSnapshot(
            bid=float(bid) if bid is not None else None,
            ask=float(ask) if ask is not None else None,
            bid_ask_spread=float(spread_absolute) if spread_absolute is not None else None,
            spread_pct=float(quote_meta.get("spread_percentage") or 0.0),
            volume_ratio=1.0,
            buy_sell_ratio=max(0.1, 1.0 - min(float(quote_meta.get("spread_percentage") or 0.0) * 10.0, 0.5)),
            buy_pressure=float(signal_meta.get("composite_score") or 0.0),
            market_signal=float(signal_meta.get("composite_score") or 0.0),
            last_price=float(quote_meta.get("current_price")) if quote_meta.get("current_price") is not None else None,
            price_timestamp=quote_meta.get("market_timestamp"),
        )
    return snapshots


def build_catalyst_frame(news_df: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "article_id",
        "url",
        "source",
        "published_at",
        "primary_symbol",
        "affected_symbols",
        "catalyst_type",
        "primary_catalyst",
        "secondary_catalysts",
        "event_title",
        "event_summary",
        "catalyst_direction",
        "catalyst_impact_score",
        "catalyst_impact_label",
        "catalyst_confidence",
        "catalyst_time_horizon",
        "novelty_score",
        "novelty_label",
        "recency_score",
        "freshness_label",
        "event_group_id",
        "classifier",
        "classifier_version",
        "evidence_tags",
        "created_at",
        "catalyst_priority",
        "related_article_count",
        "related_sources",
    ]
    if news_df.empty:
        return pd.DataFrame(columns=columns)
    inputs = build_catalyst_inputs_from_news_frame(news_df)
    records = catalyst_results_to_records(catalyst_intelligence_service.analyze(inputs))
    frame = pd.DataFrame(records, columns=columns)
    if not frame.empty:
        frame["published_at"] = pd.to_datetime(frame["published_at"], errors="coerce")
        frame["created_at"] = pd.to_datetime(frame["created_at"], errors="coerce")
    return frame


def enrich_news_with_catalysts(news_df: pd.DataFrame, catalyst_df: pd.DataFrame) -> pd.DataFrame:
    if news_df.empty or catalyst_df.empty:
        return news_df.copy()
    work = news_df.copy()
    work["_article_id"] = work["id"].astype(str) if "id" in work.columns else work.get("dedupe_hash", pd.Series("", index=work.index)).astype(str)
    catalyst_cols = [
        "article_id",
        "primary_symbol",
        "catalyst_type",
        "primary_catalyst",
        "secondary_catalysts",
        "event_title",
        "event_summary",
        "catalyst_direction",
        "catalyst_impact_score",
        "catalyst_impact_label",
        "catalyst_confidence",
        "catalyst_time_horizon",
        "novelty_score",
        "novelty_label",
        "recency_score",
        "freshness_label",
        "event_group_id",
        "classifier",
        "classifier_version",
        "evidence_tags",
        "catalyst_priority",
        "related_article_count",
        "related_sources",
    ]
    enriched = work.merge(
        catalyst_df[catalyst_cols].drop_duplicates(subset=["article_id"]),
        left_on="_article_id",
        right_on="article_id",
        how="left",
        suffixes=("", "_catalyst"),
    )
    return enriched.drop(columns=["_article_id"])


def build_dashboard_state(
    focus_ticker: str,
    compare_tickers: list[str] | None,
    horizon: str,
    start_date: str | None,
    end_date: str | None,
) -> DashboardState:
    data_mode = detect_data_mode()
    local_summary = get_local_research_summary()
    selected = normalize_tickers([focus_ticker, *(compare_tickers or [])])
    if data_mode in {DATA_MODE_LIVE, DATA_MODE_MIXED}:
        ensure_live_data(selected)
    all_news_df, price_df, quote_meta_map, signal_meta_map = load_live_data(selected)
    fresh_news_df = filter_to_fresh_news(all_news_df)
    widened_news_df = expand_sparse_news_window(all_news_df, fresh_news_df, selected, horizon)
    snapshot_map = build_snapshot_map(selected, quote_meta_map, signal_meta_map)
    news_df, price_df = filter_to_window(widened_news_df, price_df, horizon, start_date, end_date)
    catalyst_df = build_catalyst_frame(news_df)
    news_df = enrich_news_with_catalysts(news_df, catalyst_df)
    event_df = build_event_frame(news_df, price_df)
    daily_summary_df = build_grouped_daily_summary(event_df)
    compare_df = build_compare_frame(news_df, price_df, event_df, snapshot_map, quote_meta_map, signal_meta_map, catalyst_df)
    sector_df = build_sector_frame(compare_df)

    focus_symbol = _symbol_from_value(focus_ticker)
    focus_quote_meta = quote_meta_map.get(focus_ticker, {})
    focus_bars_status = _derive_bars_status(focus_ticker, price_df, focus_quote_meta)
    focus_news_quality = _derive_news_quality(news_df[news_df["ticker"] == focus_ticker]) if not news_df.empty else "unavailable"

    if data_mode == DATA_MODE_LIVE:
        data_status = "LIVE DATA: provider-backed market/news refresh is active. Research artifacts remain available on the Research page."
    elif data_mode == DATA_MODE_LOCAL and (not news_df.empty or not price_df.empty or signal_meta_map):
        data_status = (
            "ALPACA - UNCONFIGURED. LOCAL RESEARCH DATA is available as a fallback; no live quote is being fabricated."
        )
    elif data_mode == DATA_MODE_MIXED:
        data_status = "ALPACA LIVE - AVAILABLE when credentials are configured; local research data is retained as validation/fallback."
    elif not compare_df.empty and any(compare_df["mode"] == "News + Quote Quality"):
        data_status = "News signal with quote-quality adjustment is active for at least one selected ticker."
    elif focus_symbol is not None and focus_symbol.exchange in {"NSE", "BSE"} and focus_quote_meta and focus_bars_status == "unavailable":
        data_status = (
            f"{focus_symbol.exchange} quote is live, but historical bars are unavailable for overlap analysis. "
            f"News quality is {focus_news_quality}."
        )
    elif any(_is_usable_quote_meta(meta) for meta in quote_meta_map.values()):
        data_status = "Quote-quality fallback: usable quotes exist, but fresh relevant headlines are limited."
    elif not news_df.empty:
        data_status = "News-only signal: recent headlines exist, but current market quotes are unavailable."
    else:
        data_status = "Unavailable: no fresh provider data is currently available for the selected workspace."

    return DashboardState(
        news_df=news_df,
        price_df=price_df,
        event_df=event_df,
        daily_summary_df=daily_summary_df,
        compare_df=compare_df,
        sector_df=sector_df,
        catalyst_df=catalyst_df,
        snapshot_map=snapshot_map,
        quote_meta_map=quote_meta_map,
        signal_meta_map=signal_meta_map,
        demo_mode=data_mode in {DATA_MODE_LOCAL, DATA_MODE_MIXED},
        data_status=data_status,
        data_mode=data_mode,
        local_summary=local_summary,
    )


def filter_to_window(
    news_df: pd.DataFrame,
    price_df: pd.DataFrame,
    horizon: str,
    start_date: str | None,
    end_date: str | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if news_df.empty and price_df.empty:
        return news_df, price_df

    if start_date or end_date:
        start_ts = pd.to_datetime(start_date) if start_date else None
        end_ts = pd.to_datetime(end_date) + pd.Timedelta(days=1) if end_date else None
        window_days = 30
    else:
        anchor = None
        if not news_df.empty:
            anchor = news_df["published_at"].max()
        elif not price_df.empty:
            anchor = price_df["timestamp"].max()
        lookback_days = HORIZON_DAYS.get(horizon, 7)
        window_days = lookback_days
        start_ts = anchor - pd.Timedelta(days=lookback_days) if anchor is not None else None
        end_ts = anchor + pd.Timedelta(days=1) if anchor is not None else None

    original_news_df = news_df.copy()
    original_price_df = price_df.copy()
    if start_ts is not None and not news_df.empty:
        news_df = news_df[news_df["published_at"] >= start_ts]
    if end_ts is not None and not news_df.empty:
        news_df = news_df[news_df["published_at"] <= end_ts]
    if start_ts is not None and not price_df.empty:
        price_df = price_df[price_df["timestamp"] >= start_ts]
    if end_ts is not None and not price_df.empty:
        price_df = price_df[price_df["timestamp"] <= end_ts]

    if price_df.empty and not original_price_df.empty:
        fallback_frames: list[pd.DataFrame] = []
        for ticker in sorted(original_price_df["ticker"].dropna().unique()):
            ticker_prices = original_price_df[original_price_df["ticker"] == ticker].copy()
            if ticker_prices.empty:
                continue
            latest_timestamp = ticker_prices["timestamp"].max()
            fallback_start = latest_timestamp - pd.Timedelta(days=window_days)
            fallback_subset = ticker_prices[ticker_prices["timestamp"] >= fallback_start]
            if not fallback_subset.empty:
                fallback_frames.append(fallback_subset)
        if fallback_frames:
            price_df = pd.concat(fallback_frames, ignore_index=True)
    if news_df.empty and not original_news_df.empty:
        fallback_frames = []
        for ticker in sorted(original_news_df["ticker"].dropna().unique()):
            ticker_news = original_news_df[original_news_df["ticker"] == ticker].copy()
            if ticker_news.empty:
                continue
            latest_timestamp = ticker_news["published_at"].max()
            fallback_start = latest_timestamp - pd.Timedelta(days=window_days)
            fallback_subset = ticker_news[ticker_news["published_at"] >= fallback_start]
            if not fallback_subset.empty:
                fallback_frames.append(fallback_subset)
        if fallback_frames:
            news_df = pd.concat(fallback_frames, ignore_index=True)
    return news_df.copy(), price_df.copy()


def build_event_frame(news_df: pd.DataFrame, price_df: pd.DataFrame) -> pd.DataFrame:
    if news_df.empty or price_df.empty:
        return pd.DataFrame()
    events: list[pd.DataFrame] = []
    for ticker in sorted(news_df["ticker"].dropna().unique()):
        ticker_news = news_df[news_df["ticker"] == ticker]
        ticker_prices = price_df[price_df["ticker"] == ticker]
        if ticker_news.empty or ticker_prices.empty:
            continue
        joined = align_news_with_prices(ticker_news, ticker_prices, return_window_minutes=60)
        if not joined.empty:
            joined["confidence_pct"] = confidence_series(joined) * 100.0
            joined["impact_pct"] = joined["forward_return"].fillna(0.0) * 100.0
            events.append(joined)
    return pd.concat(events, ignore_index=True) if events else pd.DataFrame()


def build_grouped_daily_summary(event_df: pd.DataFrame) -> pd.DataFrame:
    if event_df.empty:
        return pd.DataFrame()
    frames: list[pd.DataFrame] = []
    for ticker in sorted(event_df["ticker"].dropna().unique()):
        ticker_df = event_df[event_df["ticker"] == ticker]
        summary = build_daily_impact_summary(ticker_df)
        if not summary.empty:
            summary["ticker"] = ticker
            frames.append(summary)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def build_compare_frame(
    news_df: pd.DataFrame,
    price_df: pd.DataFrame,
    event_df: pd.DataFrame,
    snapshot_map: dict[str, MarketSignalSnapshot] | None = None,
    quote_meta_map: dict[str, dict[str, object]] | None = None,
    signal_meta_map: dict[str, dict[str, object]] | None = None,
    catalyst_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    tickers = sorted(
        set(news_df.get("ticker", pd.Series(dtype=str)).dropna().tolist())
        | set(price_df.get("ticker", pd.Series(dtype=str)).dropna().tolist())
        | set((quote_meta_map or {}).keys())
    )
    rows: list[dict[str, object]] = []

    for ticker in tickers:
        symbol = _symbol_from_value(ticker)
        ticker_news = news_df[news_df["ticker"] == ticker]
        ticker_prices = price_df[price_df["ticker"] == ticker]
        ticker_events = event_df[event_df["ticker"] == ticker] if not event_df.empty else pd.DataFrame()
        ticker_catalysts = catalyst_df[catalyst_df["primary_symbol"] == ticker] if catalyst_df is not None and not catalyst_df.empty else pd.DataFrame()
        snapshot = (snapshot_map or {}).get(ticker)
        quote_meta = (quote_meta_map or {}).get(ticker, {})
        signal_meta = (signal_meta_map or {}).get(ticker, {})
        bars_status = _derive_bars_status(ticker, price_df, quote_meta)
        news_quality = _derive_news_quality(ticker_news)
        live_v2 = signal_meta.get("live_v2") if isinstance(signal_meta.get("live_v2"), dict) else {}

        recent_close = latest_recent_close(ticker_prices)
        historical_close = float(ticker_prices["close"].iloc[-1]) if not ticker_prices.empty else np.nan
        current_price = (
            float(quote_meta.get("current_price"))
            if quote_meta.get("current_price") is not None
            else recent_close
            if recent_close is not None
            else historical_close
        )
        first_close = float(ticker_prices["close"].iloc[0]) if not ticker_prices.empty else np.nan
        last_close = float(ticker_prices["close"].iloc[-1]) if not ticker_prices.empty else current_price
        pct_change = ((last_close - first_close) / first_close) * 100.0 if pd.notna(first_close) and first_close else 0.0

        if not ticker_news.empty:
            avg_sentiment = float(ticker_news["sentiment_score"].mean())
            avg_confidence = float(confidence_series(ticker_news).mean() * 100.0)
            news_volume = int(len(ticker_news))
        else:
            avg_sentiment = float(signal_meta.get("composite_score") or snapshot.market_signal if snapshot is not None else 0.0)
            raw_conf = signal_meta.get("signal_confidence")
            avg_confidence = float(raw_conf) * 100.0 if raw_conf is not None else np.nan
            news_volume = 0

        top_catalyst = {}
        if not ticker_catalysts.empty:
            top_row = ticker_catalysts.sort_values("catalyst_priority", ascending=False).iloc[0]
            top_catalyst = {
                "count": int(ticker_catalysts["event_group_id"].nunique()) if "event_group_id" in ticker_catalysts.columns else int(len(ticker_catalysts)),
                "type": str(top_row.get("catalyst_type") or "UNKNOWN"),
                "direction": str(top_row.get("catalyst_direction") or "UNKNOWN"),
                "impact": str(top_row.get("catalyst_impact_label") or "LOW"),
                "title": str(top_row.get("event_title") or top_row.get("title") or ""),
            }

        rows.append(
            {
                "ticker": ticker,
                "name": symbol.display_name if symbol is not None else ticker,
                "sector": symbol.sector if symbol is not None else "Other",
                "exchange": symbol.exchange if symbol is not None else get_exchange_for_ticker(ticker),
                "currency": quote_meta.get("currency") or ("USD" if (symbol and symbol.exchange == "US") else "INR"),
                "last_close": current_price,
                "pct_change": pct_change,
                "news_volume": news_volume,
                "avg_sentiment": avg_sentiment,
                "avg_confidence": avg_confidence,
                "avg_impact_pct": float(ticker_events["impact_pct"].mean()) if not ticker_events.empty else 0.0,
                "avg_spread_pct": float((quote_meta.get("spread_percentage") or 0.0) * 100.0),
                "avg_volume_ratio": float(volume_ratio_series(ticker_news).mean()) if not ticker_news.empty else 1.0,
                "avg_buy_sell_ratio": float(buy_sell_ratio_series(ticker_news).mean()) if not ticker_news.empty else float(snapshot.buy_sell_ratio if snapshot is not None else 1.0),
                "avg_market_signal": float(signal_meta.get("composite_score") or snapshot.market_signal if snapshot is not None else 0.0),
                "volume": float(quote_meta.get("volume") or (ticker_prices["volume"].iloc[-1] if not ticker_prices.empty else 0.0)),
                "quote_provider": quote_meta.get("provider") or "unavailable",
                "quote_quality": quote_meta.get("quality_status") or "unavailable",
                "bars_status": bars_status,
                "news_quality": news_quality,
                "freshness_seconds": quote_meta.get("freshness_seconds"),
                "freshness_label": quote_meta.get("freshness_label") or "UNKNOWN",
                "market_status": quote_meta.get("market_status") or "UNKNOWN",
                "feed": quote_meta.get("feed") or "",
                "mode": signal_meta.get("mode") or ("Quote-quality fallback" if _is_usable_quote_meta(quote_meta) else "Unavailable"),
                "signal_label": signal_meta.get("composite_label") or label_for_signal(avg_sentiment),
                "signal_confidence": signal_meta.get("signal_confidence"),
                "v2_score": live_v2.get("score") if live_v2 else np.nan,
                "v2_label": live_v2.get("label") if live_v2 else "unavailable",
                "v2_confidence": live_v2.get("confidence") if live_v2 else np.nan,
                "final_reason": signal_meta.get("final_reason") or "",
                "catalyst_count": top_catalyst.get("count", 0),
                "top_catalyst": top_catalyst.get("type", "UNKNOWN"),
                "top_catalyst_direction": top_catalyst.get("direction", "UNKNOWN"),
                "top_catalyst_impact": top_catalyst.get("impact", "n/a"),
                "top_catalyst_title": top_catalyst.get("title", ""),
            }
        )
    return pd.DataFrame(rows, columns=COMPARE_COLUMNS)


def build_sector_frame(compare_df: pd.DataFrame) -> pd.DataFrame:
    if compare_df.empty:
        return pd.DataFrame()
    return (
        compare_df.groupby("sector", as_index=False)
        .agg(
            sentiment=("avg_sentiment", "mean"),
            performance=("pct_change", "mean"),
            confidence=("avg_confidence", "mean"),
        )
        .sort_values("sentiment", ascending=False)
    )


def compute_market_mood(compare_df: pd.DataFrame) -> tuple[str, int, str]:
    if compare_df.empty:
        return "Neutral", 50, "Insufficient local or live data for a workspace-wide reading."
    mood_value = int(np.clip(((compare_df["avg_sentiment"].mean() + 1.0) / 2.0) * 100.0, 0, 100))
    if mood_value >= 60:
        return "Bullish", mood_value, "Stored news and composite signals lean positive across the tracked names."
    if mood_value <= 40:
        return "Bearish", mood_value, "Stored news and composite signals lean negative across the tracked names."
    return "Balanced", mood_value, "Signals are mixed and no strong broad-market edge is visible."


def build_ai_explanation(focus_ticker: str, news_df: pd.DataFrame, compare_df: pd.DataFrame) -> list[str]:
    ticker_news = news_df[news_df["ticker"] == focus_ticker].sort_values("published_at", ascending=False)
    compare_row = compare_df[compare_df["ticker"] == focus_ticker]
    mode = compare_row["mode"].iloc[0] if not compare_row.empty else "Unavailable"
    quality = compare_row["quote_quality"].iloc[0] if not compare_row.empty else "unavailable"
    exchange = compare_row["exchange"].iloc[0] if not compare_row.empty else get_exchange_for_ticker(focus_ticker)

    if ticker_news.empty:
        return [
            f"{get_company_name(focus_ticker)} has no stored headlines inside the selected research window.",
            f"The workspace is operating in {mode.lower()} mode, with quote quality marked {quality}.",
            f"{exchange} selections may still show live quotes even when bar overlap analysis is not available.",
            "Signal confidence is intentionally labeled as historical when the app cannot ground the move in live provider data.",
        ]

    avg_sentiment = float(ticker_news["sentiment_score"].mean())
    direction = "bullish" if avg_sentiment > 0.15 else "bearish" if avg_sentiment < -0.15 else "neutral"
    avg_confidence = float(confidence_series(ticker_news).mean() * 100.0)
    avg_buy_sell = float(buy_sell_ratio_series(ticker_news).mean())
    avg_volume_ratio = float(volume_ratio_series(ticker_news).mean())
    latest = ticker_news.iloc[0]
    catalyst_type = str(latest.get("catalyst_type") or latest.get("catalyst_tag") or "UNKNOWN").replace("_", " ").title()
    catalyst_direction = str(latest.get("catalyst_direction") or "UNKNOWN").title()
    catalyst_impact = str(latest.get("catalyst_impact_label") or "n/a").replace("_", " ").title()

    lines = [
        f"{get_company_name(focus_ticker)} currently reads as a {direction} short-term signal.",
        f"Stored analyzed headlines average {avg_confidence:.0f}% model confidence; quote-quality proxies show spread-derived liquidity near {avg_buy_sell:.2f}x and stored volume context around {avg_volume_ratio:.2f}x.",
        f"Latest driver: {latest['title']}",
        f"Catalyst lens: {catalyst_type} event, {catalyst_direction.lower()} direction, {catalyst_impact.lower()} materiality.",
    ]
    if pd.notna(latest.get("short_reason")) and str(latest.get("short_reason")).strip():
        lines.append(f"Why it matters: {latest['short_reason']}")
    return lines


def build_alerts(compare_df: pd.DataFrame, event_df: pd.DataFrame, alert_threshold: int) -> list[dict[str, str]]:
    alerts: list[dict[str, str]] = []
    for _, row in compare_df.iterrows():
        sentiment_index = int(np.clip(((row["avg_sentiment"] + 1.0) / 2.0) * 100.0, 0, 100))
        if row["signal_label"] == "bearish":
            alerts.append(
                {
                    "title": f'{row["name"]} flipped bearish',
                    "detail": f'Short-term signal is bearish with mode {row["mode"]} and quote quality {row["quote_quality"]}.',
                }
            )
        if pd.notna(row["avg_confidence"]) and row["avg_confidence"] >= alert_threshold:
            alerts.append(
                {
                    "title": f'{row["name"]} confidence crossed {alert_threshold}%',
                    "detail": f'Composite signal confidence is {row["avg_confidence"]:.0f}% with {int(row["news_volume"])} fresh headlines.',
                }
            )
        if row["pct_change"] <= -2.0 and row["avg_sentiment"] > 0.15:
            alerts.append(
                {
                    "title": f'{row["name"]} price/news divergence',
                    "detail": f'Price moved {row["pct_change"]:.2f}% while sentiment stayed positive, suggesting watch-level disagreement.',
                }
            )
    if not event_df.empty:
        strongest = event_df.sort_values("impact_pct").head(2)
        for _, row in strongest.iterrows():
            alerts.append(
                {
                    "title": f'Headline impact watch: {row["ticker"]}',
                    "detail": f'{row["title"]} | estimated 1h impact {row["impact_pct"]:.2f}%',
                }
            )
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for alert in alerts:
        if alert["title"] in seen:
            continue
        deduped.append(alert)
        seen.add(alert["title"])
    return deduped[:6]


def build_metric_cards(compare_df: pd.DataFrame, event_df: pd.DataFrame) -> list[dbc.Col]:
    mood_label, mood_score, mood_note = compute_market_mood(compare_df)
    avg_confidence = float(compare_df["avg_confidence"].dropna().mean()) if not compare_df.empty else 0.0
    avg_return = float(compare_df["pct_change"].mean()) if not compare_df.empty else 0.0
    avg_spread = float(compare_df["avg_spread_pct"].mean()) if not compare_df.empty else 0.0
    metrics = [
        ("Workspace Mood Index", f"{mood_score}", mood_label),
        ("Signal Confidence", f"{avg_confidence:.0f}%", "Average article/model confidence across the active workspace"),
        ("Average Window Return", f"{avg_return:.2f}%", "Selected live price window"),
        ("Average Spread", f"{avg_spread:.2f}%", mood_note),
    ]
    return build_metric_grid(metrics, column_size=3)


def build_sentiment_timeline(news_df: pd.DataFrame) -> go.Figure:
    return build_sentiment_timeline_with_title(news_df, "Sentiment Timeline")


def build_sentiment_timeline_with_title(news_df: pd.DataFrame, title: str) -> go.Figure:
    fig = go.Figure()
    sparse_series = False
    if not news_df.empty:
        work = news_df.copy()
        work["day"] = pd.to_datetime(work["published_at"], errors="coerce").dt.floor("D")
        grouped = (
            work.groupby(["ticker", "day"], as_index=False)
            .agg(sentiment=("sentiment_score", "mean"), headline_count=("title", "count"))
        )
        for ticker in sorted(grouped["ticker"].unique()):
            subset = grouped[grouped["ticker"] == ticker]
            if len(subset) <= 3:
                sparse_series = True
                fig.add_trace(
                    go.Bar(
                        x=subset["day"],
                        y=subset["sentiment"],
                        name=ticker,
                        marker_color=np.where(subset["sentiment"] >= 0, PALETTE["bull"], PALETTE["bear"]),
                        opacity=0.8,
                        customdata=subset[["headline_count"]],
                        hovertemplate="<b>%{x|%d %b %Y}</b><br>Sentiment: %{y:.2f}<br>Headlines: %{customdata[0]}<extra>%{fullData.name}</extra>",
                    )
                )
            else:
                fig.add_trace(
                    go.Scatter(
                        x=subset["day"],
                        y=subset["sentiment"],
                        mode="lines+markers",
                        name=ticker,
                        line={"width": 3},
                        customdata=subset[["headline_count"]],
                        hovertemplate="<b>%{x|%d %b %Y}</b><br>Sentiment: %{y:.2f}<br>Headlines: %{customdata[0]}<extra>%{fullData.name}</extra>",
                    )
                )
    fig.update_layout(
        title=title,
        paper_bgcolor=PALETTE["paper"],
        plot_bgcolor=PALETTE["paper"],
        font={"color": PALETTE["ink"]},
        margin={"l": 32, "r": 24, "t": 56, "b": 28},
        legend={"orientation": "h", "y": 1.12},
        barmode="group",
        xaxis={"title": "", "gridcolor": PALETTE["grid"]},
        yaxis={"title": "Sentiment Score", "gridcolor": PALETTE["grid"], "zerolinecolor": PALETTE["grid"]},
    )
    if sparse_series:
        fig.add_annotation(
            xref="paper",
            yref="paper",
            x=1,
            y=1.16,
            showarrow=False,
            xanchor="right",
            text="Sparse data shown as daily bars",
            font={"size": 12, "color": PALETTE["muted"]},
        )
    return fig


def build_overlay_chart(focus_ticker: str, price_df: pd.DataFrame, news_df: pd.DataFrame) -> go.Figure:
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    ticker_prices = price_df[price_df["ticker"] == focus_ticker]
    ticker_news = news_df[news_df["ticker"] == focus_ticker]
    if not ticker_prices.empty:
        fig.add_trace(
            go.Scatter(
                x=ticker_prices["timestamp"],
                y=ticker_prices["close"],
                mode="lines",
                name=f"{focus_ticker} Price",
                line={"color": PALETTE["line"], "width": 3},
            ),
            secondary_y=False,
        )
    if not ticker_news.empty:
        fig.add_trace(
            go.Bar(
                x=ticker_news["published_at"],
                y=ticker_news["sentiment_score"],
                name="Headline Sentiment",
                marker_color=np.where(ticker_news["sentiment_score"] >= 0, PALETTE["bull"], PALETTE["bear"]),
                opacity=0.55,
                hovertext=ticker_news["title"],
            ),
            secondary_y=True,
        )
    fig.update_layout(
        title=f"Price vs Sentiment Overlay • {focus_ticker}",
        paper_bgcolor=PALETTE["paper"],
        plot_bgcolor=PALETTE["paper"],
        font={"color": PALETTE["ink"]},
        margin={"l": 32, "r": 24, "t": 56, "b": 28},
        legend={"orientation": "h", "y": 1.1},
    )
    fig.update_xaxes(gridcolor=PALETTE["grid"])
    fig.update_yaxes(title_text="Price", secondary_y=False, gridcolor=PALETTE["grid"])
    fig.update_yaxes(title_text="Sentiment", secondary_y=True, showgrid=False)
    return fig


def build_impact_scatter(event_df: pd.DataFrame, news_df: pd.DataFrame | None = None) -> go.Figure:
    fig = go.Figure()
    fallback_news_df = pd.DataFrame()
    mixed_modes = False

    if not event_df.empty:
        for ticker in sorted(event_df["ticker"].unique()):
            subset = event_df[event_df["ticker"] == ticker]
            fig.add_trace(
                go.Scatter(
                    x=subset["sentiment_score"],
                    y=subset["impact_pct"],
                    mode="markers",
                    name=ticker,
                    marker={"size": np.clip(subset["confidence_pct"], 10, 26), "opacity": 0.75},
                    text=subset["title"],
                )
            )
        if news_df is not None and not news_df.empty and "dedupe_hash" in event_df.columns and "dedupe_hash" in news_df.columns:
            overlap_hashes = set(event_df["dedupe_hash"].dropna().astype(str).tolist())
            fallback_news_df = news_df[
                ~news_df["dedupe_hash"].fillna("").astype(str).isin(overlap_hashes)
            ].copy()
            mixed_modes = not fallback_news_df.empty
    elif news_df is not None and not news_df.empty:
        fallback_news_df = news_df.copy()

    if not fallback_news_df.empty:
        for ticker in sorted(fallback_news_df["ticker"].unique()):
            subset = fallback_news_df[fallback_news_df["ticker"] == ticker]
            fig.add_trace(
                go.Scatter(
                    x=subset["sentiment_score"],
                    y=pd.to_numeric(subset.get("impact_strength"), errors="coerce").fillna(0.0) * 100.0,
                    mode="markers",
                    name=f"{ticker} (estimated)" if mixed_modes else ticker,
                    marker={
                        "size": np.clip(confidence_series(subset) * 100.0, 10, 26),
                        "opacity": 0.75,
                        "symbol": "circle-open" if mixed_modes else "circle",
                        "line": {"width": 2, "color": PALETTE["line"]},
                    },
                    text=subset["title"],
                    hovertemplate="<b>%{text}</b><br>Sentiment: %{x:.2f}<br>Estimated impact: %{y:.2f}%<extra>%{fullData.name}</extra>",
                )
            )
    fig.update_layout(
        title="Sentiment vs Estimated Impact",
        paper_bgcolor=PALETTE["paper"],
        plot_bgcolor=PALETTE["paper"],
        font={"color": PALETTE["ink"]},
        margin={"l": 32, "r": 24, "t": 56, "b": 28},
        xaxis={"title": "Sentiment Score", "gridcolor": PALETTE["grid"]},
        yaxis={"title": "Observed / Estimated 1H Impact %", "gridcolor": PALETTE["grid"]},
    )
    return fig


def build_sector_heatmap(sector_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if not sector_df.empty:
        fig.add_trace(
            go.Heatmap(
                z=[sector_df["sentiment"].tolist()],
                x=sector_df["sector"].tolist(),
                y=["Sector Mood"],
                text=[[
                    f'{row["sector"]}<br>Sentiment {row["sentiment"]:.2f}<br>Return {row["performance"]:.2f}%'
                    for _, row in sector_df.iterrows()
                ]],
                hoverinfo="text",
                colorscale=[[0.0, "#c0392b"], [0.5, "#f3d9a6"], [1.0, "#148f77"]],
                zmin=-1,
                zmax=1,
            )
        )
    fig.update_layout(
        title="Sector Heatmap",
        paper_bgcolor=PALETTE["paper"],
        plot_bgcolor=PALETTE["paper"],
        font={"color": PALETTE["ink"]},
        margin={"l": 24, "r": 24, "t": 56, "b": 28},
    )
    return fig


def build_compare_chart(compare_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if not compare_df.empty:
        ordered = compare_df.sort_values("pct_change", ascending=False)
        v2_values = pd.to_numeric(ordered.get("v2_score"), errors="coerce")
        fig.add_trace(go.Bar(x=ordered["ticker"], y=ordered["avg_sentiment"], name="V1 / Sentiment", marker_color=PALETTE["bull"]))
        fig.add_trace(go.Bar(x=ordered["ticker"], y=v2_values, name="V2 Score", marker_color=PALETTE["accent_2"]))
        fig.add_trace(go.Scatter(x=ordered["ticker"], y=ordered["news_volume"], name="Article Volume", mode="lines+markers", line={"color": PALETTE["line"], "width": 3}, marker={"size": 10}, yaxis="y2"))
    fig.update_layout(
        title="Signal Snapshot",
        barmode="group",
        paper_bgcolor=PALETTE["paper"],
        plot_bgcolor=PALETTE["paper"],
        font={"color": PALETTE["ink"]},
        margin={"l": 32, "r": 24, "t": 56, "b": 28},
        xaxis={"title": "", "gridcolor": PALETTE["grid"]},
        yaxis={"title": "Signal Score", "gridcolor": PALETTE["grid"], "range": [-1, 1]},
        yaxis2={"title": "Articles", "overlaying": "y", "side": "right", "showgrid": False},
        legend={"orientation": "h", "y": 1.12},
    )
    return fig


def build_price_timeline(
    price_df: pd.DataFrame,
    focus_ticker: str | None = None,
    title: str = "Price Timeline",
    normalize: bool = False,
) -> go.Figure:
    fig = go.Figure()
    work = price_df.copy()
    if focus_ticker:
        work = work[work["ticker"] == focus_ticker]
    if not work.empty:
        for ticker in sorted(work["ticker"].unique()):
            subset = work[work["ticker"] == ticker]
            y_values = subset["close"]
            if normalize and not subset.empty:
                start_close = float(subset["close"].iloc[0])
                if start_close:
                    y_values = (subset["close"] / start_close) * 100.0
            fig.add_trace(go.Scatter(x=subset["timestamp"], y=y_values, mode="lines", name=ticker, line={"width": 3}))
    fig.update_layout(
        title=title,
        paper_bgcolor=PALETTE["paper"],
        plot_bgcolor=PALETTE["paper"],
        font={"color": PALETTE["ink"]},
        margin={"l": 32, "r": 24, "t": 56, "b": 28},
        legend={"orientation": "h", "y": 1.12},
        xaxis={"title": "", "gridcolor": PALETTE["grid"]},
        yaxis={"title": "Indexed Close (100 = start)" if normalize else "Close Price", "gridcolor": PALETTE["grid"]},
    )
    return fig


def build_recent_price_histogram(
    price_df: pd.DataFrame,
    focus_ticker: str | None = None,
    days: int = 7,
    title: str = "Last 7 Trading Days",
) -> go.Figure:
    work = price_df.copy()
    if focus_ticker:
        work = work[work["ticker"] == focus_ticker]
    if work.empty:
        return build_empty_figure(title, "No live market price history is available for the current window.")

    work["timestamp"] = pd.to_datetime(work["timestamp"], errors="coerce")
    numeric_columns = ["open", "high", "low", "close", "volume"]
    for column in numeric_columns:
        if column in work.columns:
            work[column] = pd.to_numeric(work[column], errors="coerce")
    work = work.dropna(subset=["timestamp", "close"]).sort_values("timestamp")
    if work.empty:
        return build_empty_figure(title, "No live market price history is available for the current window.")

    work["day"] = work["timestamp"].dt.floor("D")
    daily = (
        work.groupby("day", as_index=False)
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        .tail(days)
        .copy()
    )
    if daily.empty:
        return build_empty_figure(title, "No live market price history is available for the current window.")
    daily["label"] = daily["day"].dt.strftime("%d %b")
    value_floor = float(daily["close"].min()) if not daily["close"].empty else 0.0
    value_ceiling = float(daily["close"].max()) if not daily["close"].empty else 0.0
    padding = max((value_ceiling - value_floor) * 0.12, max(value_ceiling, 1.0) * 0.02)

    fig = go.Figure(
        go.Bar(
            x=daily["label"],
            y=daily["close"],
            marker_color=PALETTE["bull"],
            text=[f"{value:.2f}" for value in daily["close"]],
            textposition="outside",
            cliponaxis=False,
            customdata=daily[["high", "low", "volume"]].fillna(0.0).to_numpy(),
            hovertemplate=(
                "<b>%{x}</b><br>"
                "Close: %{y:.2f}<br>"
                "High: %{customdata[0]:.2f}<br>"
                "Low: %{customdata[1]:.2f}<br>"
                "Volume: %{customdata[2]:,.0f}<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        title=title,
        paper_bgcolor=PALETTE["paper"],
        plot_bgcolor=PALETTE["paper"],
        font={"color": PALETTE["ink"]},
        margin={"l": 32, "r": 24, "t": 56, "b": 28},
        showlegend=False,
        bargap=0.38,
        xaxis={
            "title": "",
            "type": "category",
            "gridcolor": "rgba(0,0,0,0)",
            "tickangle": 0,
            "categoryorder": "array",
            "categoryarray": daily["label"].tolist(),
        },
        yaxis={
            "title": "Close",
            "gridcolor": PALETTE["grid"],
            "range": [max(value_floor - padding, 0.0), value_ceiling + padding],
        },
    )
    if len(daily) < days:
        fig.add_annotation(
            xref="paper",
            yref="paper",
            x=1,
            y=1.14,
            showarrow=False,
            xanchor="right",
            text=f"Showing {len(daily)} available trading days",
            font={"size": 12, "color": PALETTE["muted"]},
        )
    fig.update_traces(
        marker_line_width=0,
        hoverlabel={"bgcolor": PALETTE["paper"], "font_color": PALETTE["ink"]},
    )
    return fig


def build_metric_grid(items: list[tuple[str, str, str]], column_size: int = 3) -> list[dbc.Col]:
    return [
        dbc.Col(
            html.Div(
                [html.Div(title, className="metric-label"), html.Div(value, className="metric-value"), html.Div(note, className="metric-note")],
                className="metric-card",
            ),
            md=6,
            lg=column_size,
        )
        for title, value, note in items
    ]


def build_empty_figure(title: str, message: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        title=title,
        paper_bgcolor=PALETTE["paper"],
        plot_bgcolor=PALETTE["paper"],
        font={"color": PALETTE["ink"]},
        margin={"l": 32, "r": 24, "t": 56, "b": 28},
        xaxis={"visible": False},
        yaxis={"visible": False},
        annotations=[{"text": message, "xref": "paper", "yref": "paper", "x": 0.5, "y": 0.5, "showarrow": False, "font": {"size": 14, "color": PALETTE["muted"]}}],
    )
    return fig


def build_summary_list(items: list[tuple[str, str]]) -> list[html.Div]:
    return [
        html.Div([html.Div(label, className="summary-label"), html.Div(value, className="summary-value")], className="summary-item")
        for label, value in items
    ]


def get_catalyst_type_options() -> list[dict[str, str]]:
    return [{"label": item.value.replace("_", " ").title(), "value": item.value} for item in CatalystType]


def get_catalyst_direction_options() -> list[dict[str, str]]:
    return [{"label": item.value.title(), "value": item.value} for item in CatalystDirection]


def build_active_catalysts(catalyst_df: pd.DataFrame, limit: int = 6) -> list[html.Div]:
    if catalyst_df.empty:
        return [
            html.Div(
                "No classified catalysts are available for the current workspace. This usually means there are no recent headlines in the selected window.",
                className="explanation-line",
            )
        ]
    rows = catalyst_df.sort_values("catalyst_priority", ascending=False).head(limit)
    return [_catalyst_row(row, include_symbol=True) for _, row in rows.iterrows()]


def build_key_catalysts(catalyst_df: pd.DataFrame, focus_ticker: str, limit: int = 3) -> list[html.Div]:
    ticker_rows = catalyst_df[catalyst_df["primary_symbol"] == focus_ticker] if not catalyst_df.empty else pd.DataFrame()
    if ticker_rows.empty:
        return [
            html.Div(
                f"No specific catalyst was classified for {focus_ticker} in the current news window.",
                className="explanation-line",
            )
        ]
    return [_catalyst_row(row, include_symbol=False) for _, row in ticker_rows.sort_values("catalyst_priority", ascending=False).head(limit).iterrows()]


def build_catalyst_summary(catalyst_df: pd.DataFrame, focus_ticker: str) -> list[html.Div]:
    ticker_rows = catalyst_df[catalyst_df["primary_symbol"] == focus_ticker] if not catalyst_df.empty else pd.DataFrame()
    if ticker_rows.empty:
        return build_summary_list(
            [
                ("Catalysts", "0"),
                ("Top Type", "n/a"),
                ("Direction", "UNKNOWN"),
                ("Impact", "n/a"),
            ]
        )
    top = ticker_rows.sort_values("catalyst_priority", ascending=False).iloc[0]
    unique_events = int(ticker_rows["event_group_id"].nunique()) if "event_group_id" in ticker_rows.columns else int(len(ticker_rows))
    return build_summary_list(
        [
            ("Catalysts", str(unique_events)),
            ("Top Type", str(top.get("catalyst_type") or "UNKNOWN").replace("_", " ").title()),
            ("Direction", str(top.get("catalyst_direction") or "UNKNOWN").title()),
            ("Impact", str(top.get("catalyst_impact_label") or "n/a").replace("_", " ").title()),
        ]
    )


def build_catalyst_timeline(catalyst_df: pd.DataFrame, focus_ticker: str, limit: int = 8) -> list[html.Div]:
    ticker_rows = catalyst_df[catalyst_df["primary_symbol"] == focus_ticker] if not catalyst_df.empty else pd.DataFrame()
    if ticker_rows.empty:
        return [html.Div("Catalyst timeline will appear once classified headlines are available.", className="explanation-line")]
    rows = ticker_rows.sort_values("published_at", ascending=False).head(limit)
    items: list[html.Div] = []
    for _, row in rows.iterrows():
        ts = pd.to_datetime(row.get("published_at"), errors="coerce")
        time_label = ts.strftime("%Y-%m-%d %H:%M") if pd.notna(ts) else "Time unavailable"
        items.append(
            html.Div(
                [
                    html.Div(time_label, className="summary-label"),
                    html.Div(str(row.get("event_title") or ""), className="summary-value"),
                    html.Div(
                        f'{str(row.get("catalyst_type") or "UNKNOWN").replace("_", " ").title()} | {row.get("catalyst_direction", "UNKNOWN")} | {row.get("catalyst_impact_label", "n/a")} | {row.get("novelty_label", "NEW")}',
                        className="metric-note",
                    ),
                ],
                className="summary-item",
            )
        )
    return items


def build_compare_catalyst_table(compare_df: pd.DataFrame) -> list[html.Div]:
    if compare_df.empty or "top_catalyst" not in compare_df.columns:
        return [html.Div("Catalyst comparison will appear once peer headlines are available.", className="explanation-line")]
    rows = compare_df.sort_values(["catalyst_count", "avg_confidence"], ascending=False)
    items: list[html.Div] = []
    for _, row in rows.iterrows():
        items.append(
            html.Div(
                [
                    html.Div(str(row.get("ticker") or ""), className="summary-label"),
                    html.Div(
                        f'{str(row.get("top_catalyst") or "UNKNOWN").replace("_", " ").title()} | {row.get("top_catalyst_direction", "UNKNOWN")} | {row.get("top_catalyst_impact", "n/a")}',
                        className="summary-value",
                    ),
                    html.Div(f'{int(row.get("catalyst_count") or 0)} event group(s). {row.get("top_catalyst_title", "")}', className="metric-note"),
                ],
                className="summary-item",
            )
        )
    return items


def _catalyst_row(row: pd.Series, *, include_symbol: bool) -> html.Div:
    symbol = f'{row.get("primary_symbol", "")} | ' if include_symbol else ""
    title = str(row.get("event_title") or "Untitled catalyst")
    detail = (
        f'{symbol}{str(row.get("catalyst_type") or "UNKNOWN").replace("_", " ").title()} | '
        f'{row.get("catalyst_direction", "UNKNOWN")} | '
        f'{row.get("catalyst_impact_label", "n/a")} | '
        f'{row.get("catalyst_time_horizon", "UNKNOWN")} | '
        f'{row.get("novelty_label", "NEW")}'
    )
    return html.Div(
        [
            html.Div(detail, className="summary-label"),
            html.Div(title, className="summary-value"),
            html.Div(f'Priority {float(row.get("catalyst_priority") or 0.0):.3f} | Group {row.get("event_group_id", "")}', className="metric-note"),
        ],
        className="summary-item",
    )


def build_buy_readout(focus_ticker: str, compare_df: pd.DataFrame) -> html.Div:
    focus_row = compare_df[compare_df["ticker"] == focus_ticker]
    if focus_row.empty:
        return html.Div(
            "No final read is available yet because the workspace does not have enough live signal data.",
            className="explanation-line",
        )

    row = focus_row.iloc[0]
    score = float(row.get("avg_sentiment") or 0.0)
    confidence = float(row.get("signal_confidence") or 0.0) * 100.0 if pd.notna(row.get("signal_confidence")) else float(row.get("avg_confidence") or 0.0)
    mode = str(row.get("mode") or "Unavailable")
    quote_quality = str(row.get("quote_quality") or "unavailable")
    news_quality = str(row.get("news_quality") or "unavailable")
    label = str(row.get("signal_label") or "neutral").strip().lower()
    pct_change = float(row.get("pct_change") or 0.0)
    reason = str(row.get("final_reason") or "").strip()

    if label in {"bullish", "positive"} and confidence >= 60 and mode == "News + Quote Quality":
        verdict = "Constructive"
        tone = f"{focus_ticker} has a constructive short-term setup right now."
    elif label in {"bearish", "negative"} and confidence >= 55:
        verdict = "Caution"
        tone = f"{focus_ticker} has a cautious short-term signal right now."
    else:
        verdict = "Watch"
        tone = f"{focus_ticker} is better treated as a watchlist name until the signal strengthens."

    confidence_text = (
        f"Signal confidence is {confidence:.0f}%"
        if pd.notna(confidence) and confidence > 0
        else "Signal confidence is still limited"
    )
    support_line = (
        f"{confidence_text}, with mode {mode}, quote quality {quote_quality}, news quality {news_quality}, "
        f"and a recent window move of {pct_change:.2f}%."
    )
    caution_line = (
        "This is a short-term project signal built from quote quality plus headline analysis, not a financial-advice recommendation."
    )
    if reason:
        support_line = f"{support_line} Primary driver: {reason}"

    return html.Div(
        [
            html.Div("Final Read", className="section-kicker"),
            html.Div(f"{verdict} • {tone}", className="summary-value", style={"textAlign": "left"}),
            html.Div(support_line, className="explanation-line"),
            html.Div(caution_line, className="explanation-line"),
        ],
        className="summary-stack",
    )


def build_news_table(event_df: pd.DataFrame, news_df: pd.DataFrame) -> pd.DataFrame:
    if news_df.empty:
        return pd.DataFrame(
            columns=[
                "Time",
                "Age",
                "Ticker",
                "Provider",
                "Source",
                "Headline",
                "Sentiment",
                "Confidence %",
                "Impact %",
                "Catalyst",
                "Catalyst Direction",
                "Catalyst Impact",
                "Catalyst Horizon",
                "Novelty",
                "Event Group",
                "Analysis",
                "Parse Status",
                "Explanation",
            ]
        )

    table_df = news_df.sort_values("published_at", ascending=False).copy()

    if not event_df.empty:
        event_cols = [
            col
            for col in ["dedupe_hash", "confidence_pct", "impact_pct", "forward_return", "market_timestamp", "future_timestamp"]
            if col in event_df.columns
        ]
        event_link = event_df[event_cols].drop_duplicates(subset=["dedupe_hash"]) if "dedupe_hash" in event_cols else pd.DataFrame()
        if not event_link.empty:
            table_df = table_df.merge(event_link, how="left", on="dedupe_hash")

    table_df["Time"] = pd.to_datetime(table_df["published_at"]).dt.strftime("%Y-%m-%d %H:%M")
    table_df["Age"] = pd.to_datetime(table_df["published_at"]).apply(format_age_from_timestamp)
    table_df["Ticker"] = table_df["ticker"]
    table_df["Provider"] = table_df.get("provider", "Unknown")
    table_df["Source"] = table_df.get("source", "Unknown")
    table_df["Headline"] = table_df["title"]
    table_df["Sentiment"] = table_df.get("sentiment_label", "neutral").astype(str).str.title()
    if "confidence_pct" in table_df.columns:
        confidence_values = pd.to_numeric(table_df["confidence_pct"], errors="coerce")
    else:
        confidence_values = pd.Series(index=table_df.index, dtype=float)
    table_df["Confidence %"] = confidence_values.fillna(confidence_series(table_df) * 100.0).round(1)
    if "impact_pct" in table_df.columns:
        impact_series = pd.to_numeric(table_df["impact_pct"], errors="coerce")
        table_df["Impact %"] = impact_series.round(2).astype(object)
        table_df.loc[impact_series.isna(), "Impact %"] = "n/a"
    else:
        table_df["Impact %"] = "n/a"
    table_df["Catalyst"] = _table_series(table_df, "catalyst_tag", "other")
    if "catalyst_type" in table_df.columns:
        table_df["Catalyst"] = table_df["catalyst_type"].fillna(table_df["Catalyst"])
    table_df["Catalyst Direction"] = _table_series(table_df, "catalyst_direction", "UNKNOWN")
    table_df["Catalyst Impact"] = _table_series(table_df, "catalyst_impact_label", "n/a")
    table_df["Catalyst Horizon"] = _table_series(table_df, "catalyst_time_horizon", "UNKNOWN")
    table_df["Novelty"] = _table_series(table_df, "novelty_label", "NEW")
    table_df["Event Group"] = _table_series(table_df, "event_group_id", "")
    table_df["Analysis"] = table_df.get("analysis_provider", "Unknown")
    table_df["Parse Status"] = table_df.get("parse_status", "n/a").fillna("n/a")
    table_df["Explanation"] = table_df.get("short_reason", "").fillna("Awaiting price linkage for this headline.")
    return table_df[
        [
            "Time",
            "Age",
            "Ticker",
            "Provider",
            "Source",
            "Headline",
            "Sentiment",
            "Confidence %",
            "Impact %",
            "Catalyst",
            "Catalyst Direction",
            "Catalyst Impact",
            "Catalyst Horizon",
            "Novelty",
            "Event Group",
            "Analysis",
            "Parse Status",
            "Explanation",
        ]
    ]


def _table_series(table_df: pd.DataFrame, column: str, default: str) -> pd.Series:
    if column in table_df.columns:
        return table_df[column].fillna(default)
    return pd.Series(default, index=table_df.index)


def build_alert_panel(alerts: list[dict[str, str]], demo_mode: bool) -> list[dbc.ListGroupItem]:
    if not alerts:
        return [dbc.ListGroupItem("No watchlist alerts in the selected window.")]
    return [
        dbc.ListGroupItem([html.Div(alert["title"], className="alert-title"), html.Div(alert["detail"], className="alert-detail")], className="alert-item")
        for alert in alerts
    ]


def get_assets_folder() -> str:
    return str(Path(__file__).with_name("assets"))
