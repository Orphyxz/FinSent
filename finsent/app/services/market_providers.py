from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from io import StringIO
import logging
from typing import Protocol

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
        )

    def fetch_price_bars(self, symbol: SymbolRecord, start: datetime, end: datetime, interval: str) -> pd.DataFrame:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])


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
            note="Kite quote snapshot",
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


class UnavailableMarketProvider(BaseMarketProvider):
    provider_name = "unavailable"

    def fetch_quote_snapshot(self, symbol: SymbolRecord) -> QuoteSnapshot:
        return self._unavailable_quote(symbol, "No market data provider configured for this exchange")


def build_market_provider(symbol: SymbolRecord) -> MarketDataProvider:
    """Legacy convenience factory; active runtime uses provider_routers.MarketDataRouter."""
    if symbol.exchange == "US":
        return PolygonMarketDataProvider()
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
