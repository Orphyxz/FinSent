"""Whole-universe market map: one batch quote request per market.

US quotes come from Alpaca's multi-symbol snapshot endpoint and Indian quotes from Yahoo
Chart's spark endpoint (20 symbols per call), so all 355 primary listings refresh in a
couple of seconds instead of hundreds of per-symbol requests.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import logging
from threading import Lock
import time

import pandas as pd
import requests

from finsent.app.config.settings import settings
from finsent.app.services.market_providers import AlpacaMarketDataProvider
from finsent.app.services.symbol_registry import SymbolRecord, registry


logger = logging.getLogger(__name__)

MAP_TTL_SECONDS = 120
_SPARK_URL = "https://query1.finance.yahoo.com/v8/finance/spark"
_SPARK_BATCH = 20

_SECTOR_ALIASES = {"Finance": "Financials", "Consumer": "Consumer Discretionary"}


@dataclass(frozen=True, slots=True)
class MapQuote:
    ticker: str
    name: str
    sector: str
    market: str
    price: float | None
    change_pct: float | None
    dollar_volume: float | None


def _sector(symbol: SymbolRecord) -> str:
    return _SECTOR_ALIASES.get(symbol.sector, symbol.sector)


def _us_quotes(symbols: list[SymbolRecord]) -> list[MapQuote]:
    if not (settings.alpaca_api_key and settings.alpaca_api_secret):
        return []
    snapshots = AlpacaMarketDataProvider().fetch_quote_snapshots(symbols)
    quotes = []
    for symbol in symbols:
        snap = snapshots.get(symbol.provider_symbol)
        price = getattr(snap, "current_price", None) if snap else None
        previous = getattr(snap, "previous_close", None) if snap else None
        volume = getattr(snap, "day_volume", None) if snap else None
        change = None if not price or not previous else price / previous - 1.0
        quotes.append(MapQuote(symbol.ticker, symbol.display_name, _sector(symbol), "US", price, change, None if not price or not volume else price * volume))
    return quotes


def _india_quotes(symbols: list[SymbolRecord]) -> list[MapQuote]:
    by_yahoo = {symbol.yahoo_symbol: symbol for symbol in symbols}
    payload: dict[str, dict] = {}
    keys = list(by_yahoo)
    for start in range(0, len(keys), _SPARK_BATCH):
        response = requests.get(
            _SPARK_URL,
            params={"symbols": ",".join(keys[start:start + _SPARK_BATCH]), "range": "5d", "interval": "1d"},
            headers={"User-Agent": "FinSent market map"},
            timeout=10,
        )
        response.raise_for_status()
        payload.update(response.json() or {})
    quotes = []
    for key, symbol in by_yahoo.items():
        item = payload.get(key) or {}
        closes = [value for value in (item.get("close") or []) if value is not None]
        price = closes[-1] if closes else None
        previous = closes[-2] if len(closes) >= 2 else None
        change = None if not price or not previous else price / previous - 1.0
        quotes.append(MapQuote(symbol.ticker, symbol.display_name, _sector(symbol), "INDIA", price, change, None))
    return quotes


_cache: dict[str, tuple[float, pd.DataFrame]] = {}
_lock = Lock()


def market_map(market: str) -> pd.DataFrame:
    """Latest price and day change for every primary listing in a market (US, INDIA or ALL)."""
    key = (market or "US").upper()
    with _lock:
        cached = _cache.get(key)
    if cached is not None and time.time() - cached[0] < MAP_TTL_SECONDS:
        return cached[1]
    quotes: list[MapQuote] = []
    try:
        if key in {"US", "ALL"}:
            quotes += _us_quotes(registry.list_symbols("US"))
        if key in {"INDIA", "ALL"}:
            quotes += _india_quotes(registry.list_symbols("INDIA"))
    except Exception as exc:  # a failed provider leaves the previous map in place
        logger.warning("Market map refresh failed: %s", type(exc).__name__)
        if cached is not None:
            return cached[1]
    frame = pd.DataFrame([asdict(quote) for quote in quotes]) if quotes else pd.DataFrame(columns=list(MapQuote.__annotations__))
    with _lock:
        _cache[key] = (time.time(), frame)
    return frame


def sector_breadth(frame: pd.DataFrame) -> pd.DataFrame:
    """Per-sector advancers, decliners and median change."""
    if frame.empty:
        return pd.DataFrame(columns=["sector", "stocks", "advancers", "decliners", "median_change"])
    work = frame.dropna(subset=["change_pct"])
    grouped = work.groupby("sector")["change_pct"]
    return (
        pd.DataFrame(
            {
                "stocks": grouped.size(),
                "advancers": grouped.apply(lambda values: int((values > 0).sum())),
                "decliners": grouped.apply(lambda values: int((values < 0).sum())),
                "median_change": grouped.median(),
            }
        )
        .reset_index()
        .sort_values("median_change", ascending=False)
    )
