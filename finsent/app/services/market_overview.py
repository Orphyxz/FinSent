"""Cached daily history, index levels and watchlist quotes for the dashboard.

Daily bars come from the same provider routers as the rest of the app (Alpaca/Polygon
for US, Kite/Yahoo for India). Indian indices are read from Yahoo Chart directly because
they are not tradable instruments in the symbol registry. Everything is cached in memory
with a short TTL so repeated page loads do not hit providers.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
from threading import RLock
import time

import pandas as pd
import requests

from finsent.app.analysis.technicals import normalize_ohlcv
from finsent.app.services.market_context import benchmark_symbol_record
from finsent.app.services.provider_routers import MarketDataRouter
from finsent.app.services.symbol_registry import SymbolRecord, registry


logger = logging.getLogger(__name__)

HISTORY_TTL_SECONDS = 15 * 60
INDEX_TTL_SECONDS = 5 * 60
HISTORY_DAYS = 400
_YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"


@dataclass(frozen=True, slots=True)
class IndexDefinition:
    key: str
    label: str
    region: str
    source_symbol: str
    note: str


INDEX_DEFINITIONS: tuple[IndexDefinition, ...] = (
    IndexDefinition("SPY", "S&P 500", "US", "SPY", "SPY ETF proxy"),
    IndexDefinition("QQQ", "Nasdaq 100", "US", "QQQ", "QQQ ETF proxy"),
    IndexDefinition("DIA", "Dow Jones", "US", "DIA", "DIA ETF proxy"),
    IndexDefinition("IWM", "Russell 2000", "US", "IWM", "IWM ETF proxy"),
    IndexDefinition("NIFTY50", "NIFTY 50", "INDIA", "^NSEI", "NSE index"),
    IndexDefinition("SENSEX", "SENSEX", "INDIA", "^BSESN", "BSE index"),
    IndexDefinition("BANKNIFTY", "NIFTY Bank", "INDIA", "^NSEBANK", "NSE index"),
)


@dataclass(frozen=True, slots=True)
class PriceSummary:
    key: str
    label: str
    region: str
    note: str
    last: float | None
    change: float | None
    change_pct: float | None
    sparkline: tuple[float, ...]
    as_of: datetime | None
    currency: str

    @property
    def available(self) -> bool:
        return self.last is not None


class _TTLCache:
    def __init__(self) -> None:
        self._lock = RLock()
        self._items: dict[object, tuple[float, object]] = {}

    def get(self, key: object, ttl: float) -> object | None:
        with self._lock:
            item = self._items.get(key)
            if item is None or time.monotonic() - item[0] > ttl:
                return None
            return item[1]

    def set(self, key: object, value: object) -> None:
        with self._lock:
            self._items[key] = (time.monotonic(), value)


_cache = _TTLCache()
_router: MarketDataRouter | None = None
_router_lock = RLock()


def _market_router() -> MarketDataRouter:
    global _router
    with _router_lock:
        if _router is None:
            _router = MarketDataRouter()
        return _router


def resolve_symbol(ticker: str) -> SymbolRecord | None:
    symbol = registry.resolve_any(ticker)
    if symbol is not None:
        return symbol
    normalized = ticker.upper().strip()
    if normalized.isalpha() and len(normalized) <= 5:
        return benchmark_symbol_record(normalized)
    return None


def daily_history(ticker: str, days: int = HISTORY_DAYS) -> pd.DataFrame:
    """Daily OHLCV bars for a registry ticker or US benchmark ETF, newest last."""
    key = ("history", ticker.upper(), days)
    cached = _cache.get(key, HISTORY_TTL_SECONDS)
    if cached is not None:
        return cached  # type: ignore[return-value]
    symbol = resolve_symbol(ticker)
    frame = normalize_ohlcv(None)
    if symbol is not None:
        end = datetime.now(timezone.utc).replace(tzinfo=None)
        try:
            result = _market_router().fetch_price_bars(symbol, start=end - timedelta(days=days), end=end, interval="1d")
            frame = normalize_ohlcv(result.data)
        except Exception as exc:  # providers fail independently; the page shows what it has
            logger.warning("Daily history unavailable for %s: %s", ticker, type(exc).__name__)
    if not frame.empty:
        _cache.set(key, frame)
    return frame


def history_between(ticker: str, start: datetime, end: datetime) -> pd.DataFrame:
    """Daily bars for a fixed historical range (used by the research event explorer)."""
    key = ("range", ticker.upper(), start.date().isoformat(), end.date().isoformat())
    cached = _cache.get(key, 24 * 3600)
    if cached is not None:
        return cached  # type: ignore[return-value]
    symbol = resolve_symbol(ticker)
    frame = normalize_ohlcv(None)
    if symbol is not None:
        try:
            result = _market_router().fetch_price_bars(symbol, start=start, end=end, interval="1d")
            frame = normalize_ohlcv(result.data)
        except Exception as exc:
            logger.warning("Historical range unavailable for %s: %s", ticker, type(exc).__name__)
    if not frame.empty:
        _cache.set(key, frame)
    return frame


def yahoo_index_history(source_symbol: str, *, range_: str = "3mo") -> pd.DataFrame:
    """Daily bars for an index Yahoo Chart publishes (NIFTY, SENSEX, NSE sector indices)."""
    key = ("yahoo-index", source_symbol, range_)
    cached = _cache.get(key, HISTORY_TTL_SECONDS)
    if cached is not None:
        return cached  # type: ignore[return-value]
    try:
        frame = _yahoo_index_history(source_symbol, range_)
    except Exception as exc:
        logger.warning("Index history unavailable for %s: %s", source_symbol, type(exc).__name__)
        frame = normalize_ohlcv(None)
    if not frame.empty:
        _cache.set(key, frame)
    return frame


def _yahoo_index_history(source_symbol: str, range_: str = "3mo") -> pd.DataFrame:
    response = requests.get(
        _YAHOO_CHART_URL.format(symbol=source_symbol),
        params={"range": range_, "interval": "1d"},
        headers={"User-Agent": "FinSent market overview"},
        timeout=10,
    )
    response.raise_for_status()
    result = ((response.json() or {}).get("chart") or {}).get("result") or []
    if not result:
        return normalize_ohlcv(None)
    timestamps = result[0].get("timestamp") or []
    quote = ((result[0].get("indicators") or {}).get("quote") or [{}])[0]
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(timestamps, unit="s"),
            "open": quote.get("open"),
            "high": quote.get("high"),
            "low": quote.get("low"),
            "close": quote.get("close"),
            "volume": quote.get("volume"),
        }
    )
    return normalize_ohlcv(frame)


def summarize_history(
    frame: pd.DataFrame,
    *,
    key: str,
    label: str,
    region: str,
    note: str,
    currency: str,
    points: int = 30,
) -> PriceSummary:
    closes = frame["close"].dropna() if not frame.empty else pd.Series(dtype=float)
    if closes.empty:
        return PriceSummary(key, label, region, note, None, None, None, (), None, currency)
    last = float(closes.iloc[-1])
    previous = float(closes.iloc[-2]) if len(closes) >= 2 else None
    change = None if previous is None else last - previous
    change_pct = None if not previous else last / previous - 1.0
    as_of = pd.Timestamp(frame["timestamp"].iloc[-1]).to_pydatetime()
    return PriceSummary(key, label, region, note, last, change, change_pct, tuple(float(v) for v in closes.tail(points)), as_of, currency)


def _index_summary(definition: IndexDefinition) -> PriceSummary:
    currency = "INR" if definition.region == "INDIA" else "USD"
    try:
        frame = daily_history(definition.source_symbol, days=120) if definition.region == "US" else yahoo_index_history(definition.source_symbol)
    except Exception as exc:
        logger.warning("Index %s unavailable: %s", definition.key, type(exc).__name__)
        frame = normalize_ohlcv(None)
    return summarize_history(frame, key=definition.key, label=definition.label, region=definition.region, note=definition.note, currency=currency)


def index_summaries() -> list[PriceSummary]:
    cached = _cache.get("indices", INDEX_TTL_SECONDS)
    if cached is not None:
        return cached  # type: ignore[return-value]
    with ThreadPoolExecutor(max_workers=len(INDEX_DEFINITIONS)) as pool:
        summaries = list(pool.map(_index_summary, INDEX_DEFINITIONS))
    if any(item.available for item in summaries):
        _cache.set("indices", summaries)
    return summaries


def watchlist_summaries(tickers: list[str]) -> list[PriceSummary]:
    def one(ticker: str) -> PriceSummary:
        symbol = registry.resolve_any(ticker)
        currency = "INR" if symbol is not None and symbol.exchange in {"NSE", "BSE"} else "USD"
        label = symbol.display_name if symbol is not None else ticker
        region = "INDIA" if currency == "INR" else "US"
        return summarize_history(daily_history(ticker, days=60), key=ticker, label=label, region=region, note="daily bars", currency=currency)

    if not tickers:
        return []
    with ThreadPoolExecutor(max_workers=min(8, len(tickers))) as pool:
        return list(pool.map(one, tickers))


def warm_caches(tickers: list[str]) -> None:
    """Fill the history and index caches in the background so the first page load is fast."""
    try:
        index_summaries()
        watchlist_summaries(tickers)
    except Exception as exc:
        logger.warning("Market overview warm-up failed: %s", type(exc).__name__)
