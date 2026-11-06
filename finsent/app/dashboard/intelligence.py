"""Market-wide aggregates for the executive overview and the compare page.

Everything here reads stored news, sentiment and signal rows plus cached daily bars, so the
overview renders without waiting on providers. A background refresh keeps the watchlist's
stored news current at a slow cadence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from threading import Lock, Thread
import time

import numpy as np
import pandas as pd

from finsent.app.analysis.technicals import annualized_volatility, technical_snapshot
from finsent.app.dashboard import view_model as vm
from finsent.app.services import market_overview
from finsent.app.services.market_overview import PriceSummary


logger = logging.getLogger(__name__)

WATCHLISTS = {
    "US": ["AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA", "JPM"],
    "INDIA": ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "SBIN", "BHARTIARTL", "ITC"],
}
WATCHLISTS["ALL"] = WATCHLISTS["US"][:5] + WATCHLISTS["INDIA"][:5]
SNAPSHOT_TTL_SECONDS = 60
BACKGROUND_REFRESH_SECONDS = 15 * 60


def watchlist_for_market(market: str | None) -> list[str]:
    return list(WATCHLISTS.get((market or "US").upper(), WATCHLISTS["US"]))


@dataclass(slots=True)
class WatchRow:
    ticker: str
    name: str
    currency: str
    price: PriceSummary
    sentiment: float | None
    sentiment_change: float | None
    articles_24h: int
    articles_total: int
    v1_label: str
    v2_label: str
    v2_score: float | None
    rsi: float | None = None
    return_1m: float | None = None
    volatility: float | None = None


@dataclass(slots=True)
class ExecutiveSnapshot:
    market: str
    rows: list[WatchRow]
    indices: list[PriceSummary]
    mood_label: str
    mood_score: float | None
    positive_catalysts: pd.DataFrame
    negative_catalysts: pd.DataFrame
    todays_events: pd.DataFrame
    signal_counts: dict[str, dict[str, int]]
    articles_analyzed: int
    built_at: float = field(default_factory=time.time)


def _signal_label(value: object) -> str:
    text = str(value or "").strip().lower()
    if text in {"bullish", "positive", "strong_bullish", "buy"}:
        return "Bullish"
    if text in {"bearish", "negative", "strong_bearish", "sell"}:
        return "Bearish"
    return "Neutral" if text else "No signal"


def mood_from_score(score: float | None) -> str:
    if score is None:
        return "No data"
    if score >= 0.12:
        return "Bullish"
    if score <= -0.12:
        return "Bearish"
    return "Neutral"


def _sentiment_window(frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> float | None:
    window = frame[(frame["published_at"] > start) & (frame["published_at"] <= end)]
    values = pd.to_numeric(window["sentiment_score"], errors="coerce").dropna()
    return None if values.empty else float(values.mean())


def _rows(tickers: list[str], news_df: pd.DataFrame, signal_meta: dict[str, dict[str, object]], prices: list[PriceSummary]) -> list[WatchRow]:
    now = pd.Timestamp.utcnow().tz_localize(None)
    price_map = {item.key: item for item in prices}
    rows: list[WatchRow] = []
    for ticker in tickers:
        frame = news_df[news_df["ticker"] == ticker] if not news_df.empty else news_df
        if not frame.empty:
            latest = frame["published_at"].max()
            # Recent sentiment versus the three days before it; anchored on the latest
            # article so a quiet day does not read as a collapse in sentiment.
            recent = _sentiment_window(frame, latest - pd.Timedelta(hours=24), latest)
            prior = _sentiment_window(frame, latest - pd.Timedelta(hours=96), latest - pd.Timedelta(hours=24))
            overall = _sentiment_window(frame, latest - pd.Timedelta(days=7), latest)
            articles_24h = int((frame["published_at"] > now - pd.Timedelta(hours=24)).sum())
        else:
            recent = prior = overall = None
            articles_24h = 0
        meta = signal_meta.get(ticker, {})
        live_v2 = meta.get("live_v2") or {}
        symbol = vm._symbol_from_value(ticker)
        technicals = technical_snapshot(market_overview.daily_history(ticker, days=60))
        rows.append(
            WatchRow(
                ticker=ticker,
                name=symbol.display_name if symbol else ticker,
                currency=symbol.currency if symbol else "USD",
                price=price_map.get(ticker) or market_overview.summarize_history(pd.DataFrame(), key=ticker, label=ticker, region="US", note="", currency="USD"),
                sentiment=overall,
                sentiment_change=None if recent is None or prior is None else recent - prior,
                articles_24h=articles_24h,
                articles_total=len(frame),
                v1_label=_signal_label(meta.get("composite_label")),
                v2_label=_signal_label(live_v2.get("label")),
                v2_score=live_v2.get("score"),
                rsi=technicals.rsi_14,
                return_1m=technicals.return_1m,
                volatility=technicals.volatility_30d,
            )
        )
    return rows


def _catalyst_tables(news_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    empty = pd.DataFrame()
    if news_df.empty:
        return empty, empty, empty
    catalysts = vm.build_catalyst_frame(news_df)
    if catalysts.empty:
        return empty, empty, empty
    catalysts = catalysts.sort_values(["catalyst_priority", "published_at"], ascending=[False, False])
    catalysts = catalysts.drop_duplicates("event_group_id")
    positive = catalysts[catalysts["catalyst_direction"] == "BULLISH"].head(5)
    negative = catalysts[catalysts["catalyst_direction"] == "BEARISH"].head(5)
    latest_day = pd.to_datetime(catalysts["published_at"]).max().normalize()
    today = catalysts[
        (pd.to_datetime(catalysts["published_at"]) >= latest_day)
        & catalysts["catalyst_impact_label"].isin(["HIGH", "VERY_HIGH"])
    ].head(6)
    return positive, negative, today


_snapshot_cache: dict[str, ExecutiveSnapshot] = {}
_snapshot_lock = Lock()
_last_background_refresh: dict[str, float] = {}


def _refresh_watchlist_in_background(market: str, tickers: list[str]) -> None:
    now = time.time()
    with _snapshot_lock:
        if now - _last_background_refresh.get(market, 0.0) < BACKGROUND_REFRESH_SECONDS:
            return
        _last_background_refresh[market] = now

    def run() -> None:
        try:
            vm.ensure_live_data(tickers)
        except Exception as exc:
            logger.warning("Background watchlist refresh failed: %s", type(exc).__name__)

    Thread(target=run, name=f"watchlist-refresh-{market}", daemon=True).start()


_rebuilding: set[str] = set()


def executive_snapshot(market: str | None, tickers: list[str] | None = None) -> ExecutiveSnapshot:
    """Return the overview snapshot, serving a stale copy while a fresh one builds."""
    market_key = (market or "US").upper()
    key = market_key if not tickers else f"{market_key}:{','.join(tickers)}"
    with _snapshot_lock:
        cached = _snapshot_cache.get(key)
        stale = cached is not None and time.time() - cached.built_at >= SNAPSHOT_TTL_SECONDS
        start_rebuild = stale and key not in _rebuilding
        if start_rebuild:
            _rebuilding.add(key)
    if cached is not None:
        if start_rebuild:
            Thread(target=_rebuild, args=(key, market_key, tickers), name=f"snapshot-{market_key}", daemon=True).start()
        return cached
    return _build_snapshot(key, market_key, tickers)


def _rebuild(key: str, market: str, tickers: list[str] | None) -> None:
    try:
        _build_snapshot(key, market, tickers)
    except Exception as exc:
        logger.warning("Overview snapshot rebuild failed: %s", type(exc).__name__)
    finally:
        with _snapshot_lock:
            _rebuilding.discard(key)


def _build_snapshot(key: str, market: str | None = None, custom: list[str] | None = None) -> ExecutiveSnapshot:
    market = market or key
    tickers = list(custom) if custom else watchlist_for_market(market)
    _refresh_watchlist_in_background(key, tickers)
    news_df, _price_df, _quotes, signal_meta = vm.load_live_data(tickers)
    if not news_df.empty:
        news_df = news_df.dropna(subset=["published_at"])
    prices = market_overview.watchlist_summaries(tickers)
    rows = _rows(tickers, news_df, signal_meta, prices)
    indices = [item for item in market_overview.index_summaries() if market == "ALL" or item.region == market]

    scored = [row for row in rows if row.sentiment is not None]
    weights = np.array([max(row.articles_total, 1) for row in scored], dtype=float)
    mood_score = float(np.average([row.sentiment for row in scored], weights=weights)) if scored else None
    positive, negative, today = _catalyst_tables(news_df)
    counts: dict[str, dict[str, int]] = {"Signal V1": {}, "Signal V2": {}}
    for row in rows:
        counts["Signal V1"][row.v1_label] = counts["Signal V1"].get(row.v1_label, 0) + 1
        counts["Signal V2"][row.v2_label] = counts["Signal V2"].get(row.v2_label, 0) + 1

    snapshot = ExecutiveSnapshot(
        market=market,
        rows=rows,
        indices=indices,
        mood_label=mood_from_score(mood_score),
        mood_score=mood_score,
        positive_catalysts=positive,
        negative_catalysts=negative,
        todays_events=today,
        signal_counts=counts,
        articles_analyzed=len(news_df),
    )
    with _snapshot_lock:
        _snapshot_cache[key] = snapshot
    return snapshot


@dataclass(slots=True)
class CompareProfile:
    ticker: str
    name: str
    currency: str
    history: pd.DataFrame
    price: PriceSummary
    volatility: float | None
    sentiment: float | None
    articles: int
    sentiment_mix: dict[str, int]
    catalyst_mix: dict[str, int]
    v1_label: str
    v2_label: str
    v2_score: float | None


def compare_profiles(tickers: list[str], period_days: int = 90) -> list[CompareProfile]:
    """Per-symbol profile for up to five tickers, built from stored news and cached bars."""
    tickers = vm.normalize_tickers(tickers)[:5]
    if not tickers:
        return []
    news_df, _price_df, _quotes, signal_meta = vm.load_live_data(tickers)
    catalysts = vm.build_catalyst_frame(news_df) if not news_df.empty else pd.DataFrame()
    profiles: list[CompareProfile] = []
    for ticker in tickers:
        history = market_overview.daily_history(ticker)
        cutoff = history["timestamp"].max() - pd.Timedelta(days=period_days) if not history.empty else None
        window = history[history["timestamp"] >= cutoff] if cutoff is not None else history
        frame = news_df[news_df["ticker"] == ticker] if not news_df.empty else news_df
        labels = frame["sentiment_label"].astype(str).str.lower() if not frame.empty else pd.Series(dtype=str)
        mix = {
            "Positive": int(labels.isin(["bullish", "positive"]).sum()),
            "Neutral": int(labels.isin(["neutral", "mixed"]).sum()),
            "Negative": int(labels.isin(["bearish", "negative"]).sum()),
        }
        symbol_catalysts = catalysts[catalysts["primary_symbol"] == ticker] if not catalysts.empty else catalysts
        catalyst_mix = (
            symbol_catalysts["catalyst_type"].astype(str).str.replace("_", " ").str.title().value_counts().to_dict()
            if not symbol_catalysts.empty else {}
        )
        meta = signal_meta.get(ticker, {})
        live_v2 = meta.get("live_v2") or {}
        symbol = vm._symbol_from_value(ticker)
        scores = pd.to_numeric(frame.get("sentiment_score"), errors="coerce").dropna() if not frame.empty else pd.Series(dtype=float)
        profiles.append(
            CompareProfile(
                ticker=ticker,
                name=symbol.display_name if symbol else ticker,
                currency=symbol.currency if symbol else "USD",
                history=window,
                price=market_overview.summarize_history(history, key=ticker, label=ticker, region="", note="", currency=symbol.currency if symbol else "USD"),
                volatility=annualized_volatility(window["close"]) if not window.empty else None,
                sentiment=None if scores.empty else float(scores.mean()),
                articles=len(frame),
                sentiment_mix=mix,
                catalyst_mix={str(k): int(v) for k, v in catalyst_mix.items()},
                v1_label=_signal_label(meta.get("composite_label")),
                v2_label=_signal_label(live_v2.get("label")),
                v2_score=live_v2.get("score"),
            )
        )
    return profiles


_news_cache: dict[str, tuple[float, pd.DataFrame]] = {}


def stored_news(ticker: str, *, ttl: float = SNAPSHOT_TTL_SECONDS) -> pd.DataFrame:
    """All stored, analyzed news for one ticker (not limited to the workspace window)."""
    with _snapshot_lock:
        cached = _news_cache.get(ticker)
    if cached is not None and time.time() - cached[0] < ttl:
        return cached[1]
    news_df = vm.load_live_data([ticker])[0]
    with _snapshot_lock:
        _news_cache[ticker] = (time.time(), news_df)
    return news_df


_price_cache: dict[str, tuple[float, pd.DataFrame]] = {}


def stored_intraday(ticker: str, *, ttl: float = 30.0) -> pd.DataFrame:
    """Stored intraday bars for one ticker, read straight from the price table."""
    with _snapshot_lock:
        cached = _price_cache.get(ticker)
    if cached is not None and time.time() - cached[0] < ttl:
        return cached[1]
    symbol = vm._symbol_from_value(ticker)
    frame = pd.DataFrame()
    if symbol is not None:
        vm.init_db()
        with vm.SessionLocal() as session:
            frame = vm.PriceRepository(session).list_price_df(vm._storage_ticker(symbol))
    with _snapshot_lock:
        _price_cache[ticker] = (time.time(), frame)
    return frame
