from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from io import StringIO
import logging
from typing import Protocol
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from finsent.app.config.settings import settings
from finsent.app.services.provider_status import DataSourceState, ProviderStatus
from finsent.app.services.symbol_registry import SymbolRecord


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class QuoteSnapshot:
    symbol: str
    exchange: str
    provider_symbol: str
    current_price: float | None
    currency: str
    bid: float | None
    ask: float | None
    spread_absolute: float | None
    spread_percentage: float | None
    volume: float | None
    market_timestamp: datetime | None
    ingested_at: datetime
    provider: str
    freshness_seconds: int | None
    quality_status: str
    note: str
    provider_status: ProviderStatus | None = None
    latest_trade_price: float | None = None
    latest_trade_timestamp: datetime | None = None
    minute_open: float | None = None
    minute_high: float | None = None
    minute_low: float | None = None
    minute_close: float | None = None
    minute_volume: float | None = None
    day_open: float | None = None
    day_high: float | None = None
    day_low: float | None = None
    day_close: float | None = None
    day_volume: float | None = None
    previous_close: float | None = None
    absolute_change: float | None = None
    percent_change: float | None = None
    market_status: str = "UNKNOWN"
    feed: str | None = None
    retrieved_at: datetime | None = None
    freshness_label: str = "UNKNOWN"


class MarketDataProvider(Protocol):
    provider_name: str

    def fetch_quote_snapshot(self, symbol: SymbolRecord) -> QuoteSnapshot:
        ...

    def fetch_price_bars(self, symbol: SymbolRecord, start: datetime, end: datetime, interval: str) -> pd.DataFrame:
        ...


class BaseMarketProvider:
    provider_name = "unavailable"

    def _unavailable_quote(
        self,
        symbol: SymbolRecord,
        note: str,
        *,
        status: ProviderStatus | None = None,
    ) -> QuoteSnapshot:
        provider_status = status or ProviderStatus.unavailable(self.provider_name, "market_quote", note)
        return QuoteSnapshot(
            symbol=symbol.ticker,
            exchange=symbol.exchange,
            provider_symbol=symbol.provider_symbol,
            current_price=None,
            currency="INR" if symbol.exchange in {"NSE", "BSE"} else "USD",
            bid=None,
            ask=None,
            spread_absolute=None,
            spread_percentage=None,
            volume=None,
            market_timestamp=None,
            ingested_at=datetime.now(timezone.utc).replace(tzinfo=None),
            provider=self.provider_name,
            freshness_seconds=None,
            quality_status="unconfigured" if provider_status.status == DataSourceState.UNCONFIGURED else "unavailable",
            note=provider_status.message,
            provider_status=provider_status,
            market_status="UNKNOWN",
            retrieved_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )

    def fetch_price_bars(self, symbol: SymbolRecord, start: datetime, end: datetime, interval: str) -> pd.DataFrame:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])


class AlpacaMarketDataProvider(BaseMarketProvider):
    provider_name = "alpaca"

    def __init__(self, timeout: int = 15) -> None:
        self.timeout = timeout
        self.session = requests.Session()

    @property
    def feed(self) -> str:
        return (settings.alpaca_feed or "iex").strip().lower() or "iex"

    def fetch_quote_snapshot(self, symbol: SymbolRecord) -> QuoteSnapshot:
        snapshots = self.fetch_quote_snapshots([symbol])
        return snapshots.get(symbol.provider_symbol) or self._unavailable_quote(symbol, f"Alpaca snapshot returned no data for {symbol.provider_symbol}")

    def fetch_quote_snapshots(self, symbols: list[SymbolRecord]) -> dict[str, QuoteSnapshot]:
        us_symbols = [symbol for symbol in symbols if symbol.exchange == "US"]
        if not us_symbols:
            return {}
        for symbol in us_symbols:
            if not settings.alpaca_api_key or not settings.alpaca_api_secret:
                status = ProviderStatus.unconfigured(self.provider_name, "market_quote", "ALPACA_API_KEY or ALPACA_API_SECRET is not configured")
                return {symbol.provider_symbol: self._unavailable_quote(symbol, status.message, status=status)}
        response = self.session.get(
            f"{settings.alpaca_data_base_url.rstrip('/')}/v2/stocks/snapshots",
            params={"symbols": ",".join(symbol.ticker for symbol in us_symbols), "feed": self.feed},
            headers=self._headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json() or {}
        raw_snapshots = payload.get("snapshots") if isinstance(payload, dict) else {}
        if raw_snapshots is None and isinstance(payload, dict):
            raw_snapshots = payload
        results: dict[str, QuoteSnapshot] = {}
        for symbol in us_symbols:
            item = raw_snapshots.get(symbol.ticker) if isinstance(raw_snapshots, dict) else None
            if isinstance(item, dict):
                results[symbol.provider_symbol] = self._normalize_snapshot(symbol, item)
            else:
                results[symbol.provider_symbol] = self._unavailable_quote(symbol, f"Alpaca snapshot returned no data for {symbol.provider_symbol}")
        return results

    def fetch_price_bars(self, symbol: SymbolRecord, start: datetime, end: datetime, interval: str) -> pd.DataFrame:
        if symbol.exchange != "US" or not settings.alpaca_api_key or not settings.alpaca_api_secret:
            return super().fetch_price_bars(symbol, start, end, interval)
        response = self.session.get(
            f"{settings.alpaca_data_base_url.rstrip('/')}/v2/stocks/bars",
            params={
                "symbols": symbol.ticker,
                "timeframe": self._interval_to_alpaca(interval),
                "start": _iso_z(start),
                "end": _iso_z(end),
                "limit": 1000,
                "adjustment": "raw",
                "feed": self.feed,
            },
            headers=self._headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json() or {}
        bars = (payload.get("bars") or {}).get(symbol.ticker, []) if isinstance(payload, dict) else []
        rows: list[dict[str, object]] = []
        for bar in bars:
            if not isinstance(bar, dict):
                continue
            timestamp = _coerce_datetime(bar.get("t"))
            if timestamp is None:
                continue
            rows.append(
                {
                    "timestamp": timestamp,
                    "Open": float(bar.get("o", 0.0)),
                    "High": float(bar.get("h", 0.0)),
                    "Low": float(bar.get("l", 0.0)),
                    "Close": float(bar.get("c", 0.0)),
                    "Volume": float(bar.get("v", 0.0)),
                }
            )
        if not rows:
            return super().fetch_price_bars(symbol, start, end, interval)
        return pd.DataFrame(rows).set_index("timestamp")[["Open", "High", "Low", "Close", "Volume"]]

    def _normalize_snapshot(self, symbol: SymbolRecord, item: dict[str, object]) -> QuoteSnapshot:
        latest_trade = _nested(item, "latestTrade", "latest_trade")
        latest_quote = _nested(item, "latestQuote", "latest_quote")
        minute = _nested(item, "minuteBar", "minute_bar")
        daily = _nested(item, "dailyBar", "daily_bar")
        previous = _nested(item, "prevDailyBar", "prev_daily_bar")
        latest_trade_price = _coerce_float(latest_trade.get("p"))
        latest_trade_timestamp = _coerce_datetime(latest_trade.get("t"))
        minute_close = _coerce_float(minute.get("c"))
        day_close = _coerce_float(daily.get("c"))
        previous_close = _coerce_float(previous.get("c"))
        current_price = latest_trade_price or minute_close or day_close
        bid = _coerce_float(latest_quote.get("bp") or latest_quote.get("bid_price"))
        ask = _coerce_float(latest_quote.get("ap") or latest_quote.get("ask_price"))
        market_timestamp = latest_trade_timestamp or _coerce_datetime(minute.get("t")) or _coerce_datetime(daily.get("t"))
        spread_abs, spread_pct = PolygonMarketDataProvider._spread(bid, ask)
        freshness = PolygonMarketDataProvider._freshness(market_timestamp)
        market_status = classify_us_market_status()
        freshness_label = _freshness_label(freshness, market_status)
        quality = _quality_for_market(freshness, market_status, current_price is not None)
        change_abs = (current_price - previous_close) if current_price is not None and previous_close is not None else None
        change_pct = (change_abs / previous_close) if change_abs is not None and previous_close and previous_close > 0 else None
        note_prefix = "Alpaca snapshot"
        status_note = "LIVE" if quality == "live" else "LATEST AVAILABLE MARKET DATA" if market_status != "MARKET OPEN" else freshness_label.replace("_", " ")
        note = f"{note_prefix} feed={self.feed}; {status_note}; market_status={market_status}"
        provider_status = _status_for_quote(self.provider_name, "market_quote", quality, note, market_timestamp)
        return QuoteSnapshot(
            symbol=symbol.ticker,
            exchange=symbol.exchange,
            provider_symbol=symbol.provider_symbol,
            current_price=current_price,
            currency=settings.default_quote_currency_us,
            bid=bid,
            ask=ask,
            spread_absolute=spread_abs,
            spread_percentage=spread_pct,
            volume=_coerce_float(minute.get("v") or daily.get("v")),
            market_timestamp=market_timestamp,
            ingested_at=datetime.now(timezone.utc).replace(tzinfo=None),
            provider=self.provider_name,
            freshness_seconds=freshness,
            quality_status=quality,
            note=note,
            provider_status=provider_status,
            latest_trade_price=latest_trade_price,
            latest_trade_timestamp=latest_trade_timestamp,
            minute_open=_coerce_float(minute.get("o")),
            minute_high=_coerce_float(minute.get("h")),
            minute_low=_coerce_float(minute.get("l")),
            minute_close=minute_close,
            minute_volume=_coerce_float(minute.get("v")),
            day_open=_coerce_float(daily.get("o")),
            day_high=_coerce_float(daily.get("h")),
            day_low=_coerce_float(daily.get("l")),
            day_close=day_close,
            day_volume=_coerce_float(daily.get("v")),
            previous_close=previous_close,
            absolute_change=change_abs,
            percent_change=change_pct,
            market_status=market_status,
            feed=self.feed,
            retrieved_at=datetime.now(timezone.utc).replace(tzinfo=None),
            freshness_label=freshness_label,
        )

    def _headers(self) -> dict[str, str]:
        return {
            "accept": "application/json",
            "APCA-API-KEY-ID": settings.alpaca_api_key,
            "APCA-API-SECRET-KEY": settings.alpaca_api_secret,
        }

    @staticmethod
    def _interval_to_alpaca(interval: str) -> str:
        mapping = {"1d": "1Day", "1m": "1Min", "5m": "5Min", "15m": "15Min", "30m": "30Min", "60m": "1Hour"}
        return mapping.get(interval.lower().strip(), "15Min")


class PolygonMarketDataProvider(BaseMarketProvider):
    provider_name = "polygon"

    def __init__(self, timeout: int = 15) -> None:
        self.timeout = timeout
        self.session = requests.Session()

    def fetch_quote_snapshot(self, symbol: SymbolRecord) -> QuoteSnapshot:
        if symbol.exchange != "US":
            return self._unavailable_quote(symbol, "Polygon US stock snapshot only supports US symbols")
        if not settings.polygon_api_key:
            status = ProviderStatus.unconfigured(self.provider_name, "market_quote", "POLYGON_API_KEY is not configured")
            logger.warning("Market provider %s is unconfigured for %s: %s", self.provider_name, symbol.provider_symbol, status.message)
            return self._unavailable_quote(symbol, status.message, status=status)
        try:
            response = self.session.get(
                f"{settings.polygon_base_url.rstrip('/')}/v2/snapshot/locale/us/markets/stocks/tickers/{symbol.polygon_symbol or symbol.ticker}",
                params={"apiKey": settings.polygon_api_key},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            return self._fallback_quote_snapshot(symbol, f"Polygon quote snapshot unavailable: {exc}")
        ticker_payload = payload.get("ticker") or {}
        last_quote = ticker_payload.get("lastQuote") or {}
        minute = ticker_payload.get("min") or {}
        updated_raw = ticker_payload.get("updated")
        market_timestamp = self._coerce_epoch_ms(updated_raw)
        current_price = self._coerce_float(minute.get("c"))
        bid = self._coerce_float(last_quote.get("p"))
        ask = self._coerce_float(last_quote.get("P"))
        spread_abs, spread_pct = self._spread(bid, ask)
        freshness = self._freshness(market_timestamp)
        quality = "live" if freshness is not None and freshness <= 60 else "delayed" if freshness is not None else "unavailable"
        final_quality = quality if current_price is not None else "unavailable"
        provider_status = _status_for_quote(self.provider_name, "market_quote", final_quality, "Polygon single-ticker snapshot", market_timestamp)
        return QuoteSnapshot(
            symbol=symbol.ticker,
            exchange=symbol.exchange,
            provider_symbol=symbol.provider_symbol,
            current_price=current_price,
            currency=settings.default_quote_currency_us,
            bid=bid,
            ask=ask,
            spread_absolute=spread_abs,
            spread_percentage=spread_pct,
            volume=self._coerce_float(minute.get("v")),
            market_timestamp=market_timestamp,
            ingested_at=datetime.now(timezone.utc).replace(tzinfo=None),
            provider=self.provider_name,
            freshness_seconds=freshness,
            quality_status=final_quality,
            note="Polygon single-ticker snapshot",
            provider_status=provider_status,
        )

    def _fallback_quote_snapshot(self, symbol: SymbolRecord, note: str) -> QuoteSnapshot:
        last_trade = self._fetch_last_trade(symbol)
        if last_trade is not None:
            return last_trade
        prev_close = self._fetch_previous_close(symbol)
        if prev_close is not None:
            return prev_close
        return self._unavailable_quote(symbol, note)

    def _fetch_last_trade(self, symbol: SymbolRecord) -> QuoteSnapshot | None:
        try:
            response = self.session.get(
                f"{settings.polygon_base_url.rstrip('/')}/v2/last/trade/{symbol.polygon_symbol or symbol.ticker}",
                params={"apiKey": settings.polygon_api_key},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException:
            return None
        result = payload.get("results") or {}
        price = self._coerce_float(result.get("p"))
        market_timestamp = self._coerce_epoch_ns(result.get("t"))
        if price is None:
            return None
        freshness = self._freshness(market_timestamp)
        quality = "live" if freshness is not None and freshness <= 60 else "delayed" if freshness is not None else "unavailable"
        provider_status = _status_for_quote(self.provider_name, "market_quote", quality, "Polygon last trade fallback", market_timestamp)
        return QuoteSnapshot(
            symbol=symbol.ticker,
            exchange=symbol.exchange,
            provider_symbol=symbol.provider_symbol,
            current_price=price,
            currency=settings.default_quote_currency_us,
            bid=None,
            ask=None,
            spread_absolute=None,
            spread_percentage=None,
            volume=None,
            market_timestamp=market_timestamp,
            ingested_at=datetime.now(timezone.utc).replace(tzinfo=None),
            provider=self.provider_name,
            freshness_seconds=freshness,
            quality_status=quality,
            note="Polygon last trade fallback",
            provider_status=provider_status,
        )

    def _fetch_previous_close(self, symbol: SymbolRecord) -> QuoteSnapshot | None:
        try:
            response = self.session.get(
                f"{settings.polygon_base_url.rstrip('/')}/v2/aggs/ticker/{symbol.polygon_symbol or symbol.ticker}/prev",
                params={"adjusted": "true", "apiKey": settings.polygon_api_key},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException:
            return None
        results = payload.get("results") or []
        if not results:
            return None
        row = results[0]
        price = self._coerce_float(row.get("c"))
        market_timestamp = self._coerce_epoch_ms(row.get("t"))
        if price is None:
            return None
        freshness = self._freshness(market_timestamp)
        provider_status = ProviderStatus.stale_status(
            self.provider_name,
            "market_quote",
            "Polygon previous-close fallback",
            source_timestamp=market_timestamp,
        )
        return QuoteSnapshot(
            symbol=symbol.ticker,
            exchange=symbol.exchange,
            provider_symbol=symbol.provider_symbol,
            current_price=price,
            currency=settings.default_quote_currency_us,
            bid=None,
            ask=None,
            spread_absolute=None,
            spread_percentage=None,
            volume=self._coerce_float(row.get("v")),
            market_timestamp=market_timestamp,
            ingested_at=datetime.now(timezone.utc).replace(tzinfo=None),
            provider=self.provider_name,
            freshness_seconds=freshness,
            quality_status="stale" if freshness is not None else "unavailable",
            note="Polygon previous-close fallback",
            provider_status=provider_status,
        )

    def fetch_price_bars(self, symbol: SymbolRecord, start: datetime, end: datetime, interval: str) -> pd.DataFrame:
        if symbol.exchange != "US" or not settings.polygon_api_key:
            return super().fetch_price_bars(symbol, start, end, interval)
        multiplier, timespan = self._interval_to_polygon(interval)
        try:
            response = self.session.get(
                f"{settings.polygon_base_url.rstrip('/')}/v2/aggs/ticker/{symbol.polygon_symbol or symbol.ticker}/range/{multiplier}/{timespan}/{start.strftime('%Y-%m-%d')}/{end.strftime('%Y-%m-%d')}",
                params={"adjusted": "true", "sort": "asc", "limit": 5000, "apiKey": settings.polygon_api_key},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException:
            return super().fetch_price_bars(symbol, start, end, interval)
        results = payload.get("results") or []
        rows: list[dict[str, object]] = []
        for item in results:
            ts = self._coerce_epoch_ms(item.get("t"))
            if ts is None:
                continue
            rows.append(
                {
                    "timestamp": ts,
                    "Open": float(item.get("o", 0.0)),
                    "High": float(item.get("h", 0.0)),
                    "Low": float(item.get("l", 0.0)),
                    "Close": float(item.get("c", 0.0)),
                    "Volume": float(item.get("v", 0.0)),
                }
            )
        if not rows:
            return super().fetch_price_bars(symbol, start, end, interval)
        frame = pd.DataFrame(rows).set_index("timestamp")
        return frame[["Open", "High", "Low", "Close", "Volume"]]

    @staticmethod
    def _interval_to_polygon(interval: str) -> tuple[int, str]:
        normalized = interval.lower().strip()
        mapping = {"1d": (1, "day"), "30m": (30, "minute"), "15m": (15, "minute"), "5m": (5, "minute")}
        return mapping.get(normalized, (15, "minute"))

    @staticmethod
    def _coerce_float(value: object) -> float | None:
        try:
            return None if value is None else float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _coerce_epoch_ms(value: object) -> datetime | None:
        try:
            raw = int(value)
        except (TypeError, ValueError):
            return None
        return datetime.fromtimestamp(raw / 1000.0, tz=timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _coerce_epoch_ns(value: object) -> datetime | None:
        try:
            raw = int(value)
        except (TypeError, ValueError):
            return None
        return datetime.fromtimestamp(raw / 1_000_000_000.0, tz=timezone.utc).replace(tzinfo=None)

    @classmethod
    def _spread(cls, bid: float | None, ask: float | None) -> tuple[float | None, float | None]:
        if bid is None or ask is None or ask < bid:
            return None, None
        spread = ask - bid
        mid = (ask + bid) / 2.0
        spread_pct = spread / mid if mid > 0 else None
        return spread, spread_pct

    @staticmethod
    def _freshness(market_timestamp: datetime | None) -> int | None:
        if market_timestamp is None:
            return None
        return max(int((datetime.now(timezone.utc).replace(tzinfo=None) - market_timestamp).total_seconds()), 0)


class KiteMarketDataProvider(BaseMarketProvider):
    provider_name = "kite"
    _instrument_cache: dict[tuple[str, str], str] | None = None

    def __init__(self, timeout: int = 15) -> None:
        self.timeout = timeout
        self.session = requests.Session()

    def fetch_quote_snapshot(self, symbol: SymbolRecord) -> QuoteSnapshot:
        if symbol.exchange not in {"NSE", "BSE"}:
            return self._unavailable_quote(symbol, "Kite Connect only supports configured Indian exchange symbols")
        if not settings.kite_api_key or not settings.kite_access_token:
            status = ProviderStatus.unconfigured(self.provider_name, "market_quote", "KITE_API_KEY or KITE_ACCESS_TOKEN is not configured")
            logger.warning("Market provider %s is unconfigured for %s: %s", self.provider_name, symbol.provider_symbol, status.message)
            return self._unavailable_quote(symbol, status.message, status=status)
        try:
            response = self.session.get(
                f"{settings.kite_base_url.rstrip('/')}/quote",
                params={"i": symbol.provider_symbol},
                headers={
                    "X-Kite-Version": "3",
                    "Authorization": f"token {settings.kite_api_key}:{settings.kite_access_token}",
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json().get("data") or {}
        except requests.RequestException as exc:
            return self._unavailable_quote(symbol, f"Kite quote unavailable: {exc}")
        quote = payload.get(symbol.provider_symbol)
        if not isinstance(quote, dict):
            return self._unavailable_quote(symbol, f"Kite quote returned no data for {symbol.provider_symbol}")

        depth = quote.get("depth") or {}
        buy = depth.get("buy") or []
        sell = depth.get("sell") or []
        bid = float(buy[0]["price"]) if buy else None
        ask = float(sell[0]["price"]) if sell else None
        spread_abs, spread_pct = PolygonMarketDataProvider._spread(bid, ask)
        market_timestamp = self._coerce_datetime(quote.get("timestamp")) or self._coerce_datetime(quote.get("last_trade_time"))
        freshness = PolygonMarketDataProvider._freshness(market_timestamp)
        current_price = self._coerce_float(quote.get("last_price"))
        quality = "live" if freshness is not None and freshness <= 60 else "delayed" if freshness is not None else "unavailable"
        final_quality = quality if current_price is not None else "unavailable"
        provider_status = _status_for_quote(self.provider_name, "market_quote", final_quality, "Kite quote snapshot", market_timestamp)
        market_status = classify_india_market_status()
        return QuoteSnapshot(
            symbol=symbol.ticker,
            exchange=symbol.exchange,
            provider_symbol=symbol.provider_symbol,
            current_price=current_price,
            currency=settings.default_quote_currency_in,
            bid=bid,
            ask=ask,
            spread_absolute=spread_abs,
            spread_percentage=spread_pct,
            volume=self._coerce_float(quote.get("volume")),
            market_timestamp=market_timestamp,
            ingested_at=datetime.now(timezone.utc).replace(tzinfo=None),
            provider=self.provider_name,
            freshness_seconds=freshness,
            quality_status=final_quality,
            note=f"Kite quote snapshot; market_status={market_status}",
            provider_status=provider_status,
        )

    def fetch_price_bars(self, symbol: SymbolRecord, start: datetime, end: datetime, interval: str) -> pd.DataFrame:
        if symbol.exchange not in {"NSE", "BSE"}:
            return super().fetch_price_bars(symbol, start, end, interval)
        if not settings.kite_api_key or not settings.kite_access_token:
            return super().fetch_price_bars(symbol, start, end, interval)

        instrument_token = self._resolve_instrument_token(symbol)
        if instrument_token is None:
            return super().fetch_price_bars(symbol, start, end, interval)

        kite_interval = self._interval_to_kite(interval)
        try:
            response = self.session.get(
                f"{settings.kite_base_url.rstrip('/')}/instruments/historical/{instrument_token}/{kite_interval}",
                params={
                    "from": pd.Timestamp(start).strftime("%Y-%m-%d %H:%M:%S"),
                    "to": pd.Timestamp(end).strftime("%Y-%m-%d %H:%M:%S"),
                    "continuous": 0,
                    "oi": 0,
                },
                headers={
                    "X-Kite-Version": "3",
                    "Authorization": f"token {settings.kite_api_key}:{settings.kite_access_token}",
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json().get("data") or {}
        except requests.RequestException:
            return super().fetch_price_bars(symbol, start, end, interval)
        candles = payload.get("candles") or []
        rows: list[dict[str, object]] = []
        for candle in candles:
            if not isinstance(candle, list) or len(candle) < 6:
                continue
            timestamp = self._coerce_datetime(candle[0])
            if timestamp is None:
                continue
            rows.append(
                {
                    "timestamp": timestamp,
                    "Open": float(candle[1]),
                    "High": float(candle[2]),
                    "Low": float(candle[3]),
                    "Close": float(candle[4]),
                    "Volume": float(candle[5]),
                }
            )
        if not rows:
            return super().fetch_price_bars(symbol, start, end, interval)
        frame = pd.DataFrame(rows).set_index("timestamp")
        return frame[["Open", "High", "Low", "Close", "Volume"]]

    @staticmethod
    def _coerce_float(value: object) -> float | None:
        try:
            return None if value is None else float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _coerce_datetime(value: object) -> datetime | None:
        if not value:
            return None
        if isinstance(value, datetime):
            return value.replace(tzinfo=None) if value.tzinfo is None else value.astimezone(timezone.utc).replace(tzinfo=None)
        try:
            parsed = pd.Timestamp(value)
        except (TypeError, ValueError):
            return None
        if parsed.tzinfo is not None:
            parsed = parsed.tz_convert("UTC").tz_localize(None)
        return parsed.to_pydatetime()

    @classmethod
    def _interval_to_kite(cls, interval: str) -> str:
        normalized = interval.lower().strip()
        mapping = {
            "1d": "day",
            "60m": "60minute",
            "30m": "30minute",
            "15m": "15minute",
            "5m": "5minute",
            "1m": "minute",
        }
        return mapping.get(normalized, "15minute")

    def _resolve_instrument_token(self, symbol: SymbolRecord) -> str | None:
        if symbol.kite_instrument_key:
            return symbol.kite_instrument_key
        if self.__class__._instrument_cache is None:
            self.__class__._instrument_cache = self._load_instrument_cache()
        return self.__class__._instrument_cache.get((symbol.exchange, symbol.ticker))

    def _load_instrument_cache(self) -> dict[tuple[str, str], str]:
        response = self.session.get(
            f"{settings.kite_base_url.rstrip('/')}/instruments",
            headers={
                "X-Kite-Version": "3",
                "Authorization": f"token {settings.kite_api_key}:{settings.kite_access_token}",
            },
            timeout=max(self.timeout, 30),
        )
        response.raise_for_status()
        frame = pd.read_csv(
            StringIO(response.text),
            usecols=["instrument_token", "exchange", "tradingsymbol"],
        )
        cache: dict[tuple[str, str], str] = {}
        for _, row in frame.iterrows():
            exchange = str(row["exchange"]).strip().upper()
            ticker = str(row["tradingsymbol"]).strip().upper()
            token = str(row["instrument_token"]).strip()
            if exchange and ticker and token:
                cache[(exchange, ticker)] = token
        return cache


class YahooHistoricalMarketDataProvider(BaseMarketProvider):
    """Historical-only fallback using FinSent's established Yahoo Chart source."""

    provider_name = "yahoo_chart"

    def __init__(self, timeout: int = 20) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "FinSent/Phase23.1 Yahoo chart historical fallback"})

    def fetch_quote_snapshot(self, symbol: SymbolRecord) -> QuoteSnapshot:
        return self._unavailable_quote(symbol, "Yahoo Chart is configured as a historical-bars fallback only")

    def fetch_price_bars(self, symbol: SymbolRecord, start: datetime, end: datetime, interval: str) -> pd.DataFrame:
        if symbol.exchange not in {"NSE", "BSE"}:
            return super().fetch_price_bars(symbol, start, end, interval)

        yahoo_symbol = symbol.symbol_for(self.provider_name)
        response = self.session.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}",
            params={
                "period1": int((start - timedelta(days=2)).replace(tzinfo=timezone.utc).timestamp()),
                "period2": int((end + timedelta(days=2)).replace(tzinfo=timezone.utc).timestamp()),
                "interval": interval,
                "events": "history",
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        chart = (response.json() or {}).get("chart") or {}
        results = chart.get("result") or []
        if not results:
            return super().fetch_price_bars(symbol, start, end, interval)

        result = results[0]
        timestamps = result.get("timestamp") or []
        quotes = ((result.get("indicators") or {}).get("quote") or [{}])[0]
        rows: list[dict[str, object]] = []
        for index, timestamp in enumerate(timestamps):
            try:
                values = {
                    "Open": quotes["open"][index],
                    "High": quotes["high"][index],
                    "Low": quotes["low"][index],
                    "Close": quotes["close"][index],
                    "Volume": quotes["volume"][index],
                }
            except (IndexError, KeyError, TypeError):
                continue
            if any(value is None for value in values.values()):
                continue
            rows.append({"timestamp": pd.to_datetime(timestamp, unit="s", utc=True).tz_localize(None), **values})
        if not rows:
            return super().fetch_price_bars(symbol, start, end, interval)
        frame = pd.DataFrame(rows).set_index("timestamp")
        frame = frame[~frame.index.duplicated(keep="last")].sort_index()
        return frame[["Open", "High", "Low", "Close", "Volume"]].apply(pd.to_numeric, errors="coerce").dropna()


class UnavailableMarketProvider(BaseMarketProvider):
    provider_name = "unavailable"

    def fetch_quote_snapshot(self, symbol: SymbolRecord) -> QuoteSnapshot:
        return self._unavailable_quote(symbol, "No market data provider configured for this exchange")


def build_market_provider(symbol: SymbolRecord) -> MarketDataProvider:
    """Legacy convenience factory; active runtime uses provider_routers.MarketDataRouter."""
    if symbol.exchange == "US":
        return AlpacaMarketDataProvider() if settings.alpaca_api_key and settings.alpaca_api_secret else PolygonMarketDataProvider()
    if symbol.exchange in {"NSE", "BSE"}:
        return KiteMarketDataProvider()
    return UnavailableMarketProvider()


def _status_for_quote(
    provider: str,
    service: str,
    quality_status: str,
    message: str,
    source_timestamp: datetime | None,
) -> ProviderStatus:
    quality = (quality_status or "unavailable").strip().lower()
    if quality == "live":
        return ProviderStatus.available_status(provider, service, message, source_timestamp=source_timestamp)
    if quality == "delayed":
        return ProviderStatus.degraded(provider, service, message, source_timestamp=source_timestamp)
    if quality == "stale":
        return ProviderStatus.stale_status(provider, service, message, source_timestamp=source_timestamp)
    return ProviderStatus.unavailable(provider, service, message)


def is_usable_quote_snapshot(quote: QuoteSnapshot | None) -> bool:
    if quote is None:
        return False
    try:
        price = float(quote.current_price) if quote.current_price is not None else None
    except (TypeError, ValueError):
        return False
    if price is None or price <= 0:
        return False
    if quote.market_timestamp is None:
        return False
    quality = (quote.quality_status or "").strip().lower()
    if quality not in {"live", "delayed", "stale"}:
        return False
    if quote.provider_status is not None and quote.provider_status.status in {
        DataSourceState.UNCONFIGURED,
        DataSourceState.UNAVAILABLE,
    }:
        return False
    return True


def classify_us_market_status(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    eastern = current.astimezone(ZoneInfo("America/New_York"))
    if eastern.weekday() >= 5:
        return "MARKET CLOSED"
    current_time = eastern.time()
    if time(4, 0) <= current_time < time(9, 30):
        return "PRE-MARKET"
    if time(9, 30) <= current_time < time(16, 0):
        return "MARKET OPEN"
    if time(16, 0) <= current_time < time(20, 0):
        return "AFTER-HOURS"
    return "MARKET CLOSED"


def classify_india_market_status(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    india_time = current.astimezone(ZoneInfo("Asia/Kolkata"))
    if india_time.weekday() >= 5:
        return "MARKET CLOSED"
    if time(9, 0) <= india_time.time() < time(9, 15):
        return "PRE-OPEN"
    if time(9, 15) <= india_time.time() < time(15, 30):
        return "MARKET OPEN"
    return "MARKET CLOSED"


def _quality_for_market(freshness_seconds: int | None, market_status: str, has_price: bool) -> str:
    if not has_price:
        return "unavailable"
    if freshness_seconds is None:
        return "unavailable"
    if market_status == "MARKET OPEN" and freshness_seconds <= settings.quote_fresh_seconds:
        return "live"
    if freshness_seconds <= settings.quote_aging_seconds:
        return "delayed"
    return "stale"


def _freshness_label(freshness_seconds: int | None, market_status: str) -> str:
    if freshness_seconds is None:
        return "UNKNOWN"
    if market_status == "MARKET OPEN" and freshness_seconds <= settings.quote_fresh_seconds:
        return "LIVE"
    if freshness_seconds <= settings.quote_aging_seconds:
        return "LATEST_AVAILABLE"
    return "STALE"


def _coerce_float(value: object) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _coerce_datetime(value: object) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value
    try:
        parsed = pd.Timestamp(str(value))
    except (TypeError, ValueError):
        return None
    if parsed.nanosecond:
        parsed = parsed.floor("us")
    if parsed.tzinfo is not None:
        parsed = parsed.tz_convert("UTC").tz_localize(None)
    return parsed.to_pydatetime()


def _iso_z(value: datetime) -> str:
    parsed = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _nested(payload: dict[str, object], *keys: str) -> dict[str, object]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return {}
