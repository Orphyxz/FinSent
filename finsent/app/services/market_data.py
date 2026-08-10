from __future__ import annotations

"""
Deprecated legacy market-data module.

This file is kept only for backward compatibility with older experiments and
should not be used by the production dashboard runtime. The active runtime path
uses:
`symbol_registry -> market_providers -> intelligence_service -> repositories -> dashboard view_model`.
"""

from datetime import datetime, timedelta, timezone
from typing import Any
import warnings

import numpy as np
import pandas as pd
import requests
import yfinance as yf

from finsent.app.config.settings import settings
from finsent.app.models.schemas import MarketSignalSnapshot


class MarketDataService:
    def __init__(self, timeout: int = 20) -> None:
        warnings.warn(
            "MarketDataService is deprecated and not used by the production FinSent dashboard runtime. "
            "Use services.market_providers via intelligence_service instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "FinSent/1.0"})

    def fetch_intraday_prices(
        self,
        ticker: str,
        start: datetime,
        end: datetime,
        interval: str | None = None,
    ) -> pd.DataFrame:
        interval = interval or settings.default_price_interval
        if self._should_use_alpaca():
            try:
                frame = self._fetch_alpaca_price_history(ticker=ticker, start=start, end=end, interval=interval)
                if not frame.empty:
                    return frame
            except requests.RequestException:
                pass
            except ValueError:
                pass
        return self._fetch_yfinance_price_history(ticker=ticker, start=start, end=end, interval=interval)

    def fetch_market_snapshot(
        self,
        ticker: str,
        price_frame: pd.DataFrame | None = None,
        reference_time: datetime | None = None,
        lookback_bars: int | None = None,
        quote_snapshot: dict[str, object] | None = None,
    ) -> MarketSignalSnapshot:
        quote_snapshot = quote_snapshot or self.fetch_quote_snapshot(ticker)
        lookback = lookback_bars or settings.signal_lookback_bars

        frame = price_frame.copy() if price_frame is not None else pd.DataFrame()
        if frame.empty:
            now = datetime.utcnow()
            frame = self.fetch_intraday_prices(
                ticker=ticker,
                start=now - timedelta(days=3),
                end=now,
            )

        if frame.empty:
            return self._empty_snapshot(quote_snapshot)

        if reference_time is not None:
            window = frame[frame.index <= pd.Timestamp(reference_time)].tail(lookback)
            if window.empty:
                window = frame.tail(lookback)
        else:
            window = frame.tail(lookback)

        if window.empty:
            return self._empty_snapshot(quote_snapshot)

        volume_ratio = self._compute_volume_ratio(window)
        buy_sell_ratio = self._compute_buy_sell_ratio(window)
        buy_pressure = self._ratio_to_signal(buy_sell_ratio)
        spread_pct = quote_snapshot["spread_pct"]
        market_signal = float(
            np.clip(
                (0.45 * buy_pressure)
                + (0.35 * self._volume_ratio_to_signal(volume_ratio))
                - (0.20 * self._spread_pct_to_penalty(spread_pct)),
                -1.0,
                1.0,
            )
        )
        last_price = self._coerce_float(quote_snapshot.get("last_price"))
        if last_price is None:
            last_price = self._coerce_float(window["Close"].iloc[-1])
        price_timestamp = self._coerce_datetime(quote_snapshot.get("price_timestamp"))
        if price_timestamp is None:
            price_timestamp = self._coerce_datetime(window.index[-1])

        return MarketSignalSnapshot(
            bid=quote_snapshot["bid"],
            ask=quote_snapshot["ask"],
            bid_ask_spread=quote_snapshot["bid_ask_spread"],
            spread_pct=spread_pct,
            volume_ratio=volume_ratio,
            buy_sell_ratio=buy_sell_ratio,
            buy_pressure=buy_pressure,
            market_signal=market_signal,
            last_price=last_price,
            price_timestamp=price_timestamp,
        )

    def fetch_quote_snapshot(self, ticker: str) -> dict[str, object]:
        if self._should_use_alpaca():
            try:
                snapshot = self._fetch_alpaca_quote_snapshot(ticker)
                if snapshot:
                    return snapshot
            except requests.RequestException:
                pass
            except ValueError:
                pass
        return self._fetch_yfinance_quote_snapshot(ticker)

    def _fetch_yfinance_price_history(
        self,
        ticker: str,
        start: datetime,
        end: datetime,
        interval: str,
    ) -> pd.DataFrame:
        padded_start = start - timedelta(days=2)
        padded_end = end + timedelta(days=2)

        frame = yf.download(
            tickers=ticker.upper(),
            start=padded_start,
            end=padded_end,
            interval=interval,
            auto_adjust=False,
            progress=False,
            threads=False,
        )
        if frame.empty:
            return frame

        if isinstance(frame.columns, pd.MultiIndex):
            frame.columns = frame.columns.get_level_values(0)

        frame.index = pd.to_datetime(frame.index)
        if getattr(frame.index, "tz", None) is not None:
            frame.index = frame.index.tz_localize(None)
        return frame[["Open", "High", "Low", "Close", "Volume"]].dropna()

    def _fetch_yfinance_quote_snapshot(self, ticker: str) -> dict[str, object]:
        ticker_obj = yf.Ticker(ticker.upper())
        info: dict[str, object] = {}
        try:
            info = ticker_obj.info or {}
        except Exception:
            info = {}

        fast_info = None
        try:
            fast_info = ticker_obj.fast_info
        except Exception:
            fast_info = None

        bid = self._coerce_float(info.get("bid"))
        ask = self._coerce_float(info.get("ask"))
        if bid is None:
            bid = self._coerce_float(self._lookup_fast_info(fast_info, "bid"))
        if ask is None:
            ask = self._coerce_float(self._lookup_fast_info(fast_info, "ask"))

        spread = None
        if bid is not None and ask is not None and ask >= bid:
            spread = ask - bid
        spread_pct = 0.0
        if spread is not None:
            mid = (ask + bid) / 2 if ask is not None and bid is not None else 0.0
            if mid > 0:
                spread_pct = spread / mid
        last_price = self._coerce_float(info.get("regularMarketPrice"))
        if last_price is None:
            last_price = self._coerce_float(info.get("currentPrice"))
        if last_price is None:
            last_price = self._coerce_float(self._lookup_fast_info(fast_info, "lastPrice"))
        if last_price is None:
            last_price = self._coerce_float(self._lookup_fast_info(fast_info, "last_price"))
        if last_price is None and bid is not None and ask is not None:
            last_price = (bid + ask) / 2.0

        return {
            "bid": bid,
            "ask": ask,
            "bid_ask_spread": spread,
            "spread_pct": spread_pct,
            "last_price": last_price,
            "price_timestamp": None,
        }

    def _fetch_alpaca_price_history(
        self,
        ticker: str,
        start: datetime,
        end: datetime,
        interval: str,
    ) -> pd.DataFrame:
        bars: list[dict[str, Any]] = []
        next_page_token: str | None = None
        while True:
            params = {
                "start": self._format_rfc3339(start - timedelta(days=2)),
                "end": self._format_rfc3339(end + timedelta(days=2)),
                "timeframe": self._interval_to_alpaca_timeframe(interval),
                "limit": 10000,
                "adjustment": "raw",
                "feed": settings.alpaca_feed,
            }
            if next_page_token:
                params["page_token"] = next_page_token

            payload = self._alpaca_get(f"/v2/stocks/{ticker.upper()}/bars", params=params)
            page_bars = payload.get("bars") or []
            if not isinstance(page_bars, list):
                break
            bars.extend(page_bars)
            next_page_token = payload.get("next_page_token")
            if not next_page_token:
                break

        frame = self._alpaca_bars_to_frame(bars)
        latest_bar = self._fetch_alpaca_latest_bar(ticker)
        if latest_bar is not None:
            latest_frame = self._alpaca_bars_to_frame([latest_bar])
            if frame.empty:
                frame = latest_frame
            elif not latest_frame.empty:
                latest_ts = latest_frame.index.max()
                frame = pd.concat([frame[frame.index < latest_ts], latest_frame]).sort_index()

        if frame.empty:
            return frame

        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end)
        return frame[(frame.index >= start_ts) & (frame.index <= end_ts)]

    def _fetch_alpaca_quote_snapshot(self, ticker: str) -> dict[str, object]:
        payload = self._alpaca_get(
            f"/v2/stocks/{ticker.upper()}/quotes/latest",
            params={"feed": settings.alpaca_feed},
        )
        quote = payload.get("quote") or {}
        if not isinstance(quote, dict):
            quote = {}

        bid = self._coerce_float(quote.get("bp"))
        ask = self._coerce_float(quote.get("ap"))
        spread = None
        if bid is not None and ask is not None and ask >= bid:
            spread = ask - bid
        spread_pct = 0.0
        if spread is not None and bid is not None and ask is not None:
            mid = (ask + bid) / 2.0
            if mid > 0:
                spread_pct = spread / mid

        latest_bar = self._fetch_alpaca_latest_bar(ticker)
        last_price = self._coerce_float(latest_bar.get("c")) if latest_bar is not None else None
        price_timestamp = self._coerce_datetime(latest_bar.get("t")) if latest_bar is not None else None
        if last_price is None and bid is not None and ask is not None:
            last_price = (bid + ask) / 2.0
        if price_timestamp is None:
            price_timestamp = self._coerce_datetime(quote.get("t"))

        return {
            "bid": bid,
            "ask": ask,
            "bid_ask_spread": spread,
            "spread_pct": spread_pct,
            "last_price": last_price,
            "price_timestamp": price_timestamp,
        }

    def _fetch_alpaca_latest_bar(self, ticker: str) -> dict[str, Any] | None:
        payload = self._alpaca_get(
            f"/v2/stocks/{ticker.upper()}/bars/latest",
            params={"feed": settings.alpaca_feed},
        )
        bar = payload.get("bar")
        return bar if isinstance(bar, dict) else None

    def _alpaca_get(self, path: str, params: dict[str, object]) -> dict[str, Any]:
        response = self.session.get(
            f"{settings.alpaca_data_base_url.rstrip('/')}{path}",
            params=params,
            headers={
                "APCA-API-KEY-ID": settings.alpaca_api_key,
                "APCA-API-SECRET-KEY": settings.alpaca_api_secret,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _alpaca_bars_to_frame(bars: list[dict[str, Any]]) -> pd.DataFrame:
        rows: list[dict[str, object]] = []
        for bar in bars:
            timestamp = bar.get("t")
            if not timestamp:
                continue
            ts = pd.Timestamp(timestamp)
            if ts.tzinfo is not None:
                ts = ts.tz_convert("UTC").tz_localize(None)
            rows.append(
                {
                    "timestamp": ts.to_pydatetime(),
                    "Open": float(bar.get("o", 0.0)),
                    "High": float(bar.get("h", 0.0)),
                    "Low": float(bar.get("l", 0.0)),
                    "Close": float(bar.get("c", 0.0)),
                    "Volume": float(bar.get("v", 0.0)),
                }
            )
        if not rows:
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
        frame = pd.DataFrame(rows).drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
        return frame.set_index("timestamp")[["Open", "High", "Low", "Close", "Volume"]]

    @staticmethod
    def _format_rfc3339(value: datetime) -> str:
        if value.tzinfo is None:
            aware = value.replace(tzinfo=timezone.utc)
        else:
            aware = value.astimezone(timezone.utc)
        return aware.isoformat().replace("+00:00", "Z")

    @staticmethod
    def _interval_to_alpaca_timeframe(interval: str) -> str:
        normalized = interval.lower().strip()
        explicit_map = {
            "1m": "1Min",
            "5m": "5Min",
            "15m": "15Min",
            "30m": "30Min",
            "60m": "1Hour",
            "90m": "90Min",
            "1h": "1Hour",
            "2h": "2Hour",
            "4h": "4Hour",
            "1d": "1Day",
        }
        if normalized in explicit_map:
            return explicit_map[normalized]
        if normalized.endswith("m") and normalized[:-1].isdigit():
            return f"{int(normalized[:-1])}Min"
        if normalized.endswith("h") and normalized[:-1].isdigit():
            hours = int(normalized[:-1])
            return f"{hours}Hour"
        if normalized.endswith("d") and normalized[:-1].isdigit():
            days = int(normalized[:-1])
            return f"{days}Day"
        return "15Min"

    @staticmethod
    def _should_use_alpaca() -> bool:
        provider = settings.live_data_provider.strip().lower()
        has_keys = bool(settings.alpaca_api_key and settings.alpaca_api_secret)
        if provider == "alpaca":
            return has_keys
        if provider == "auto":
            return has_keys
        return False

    @staticmethod
    def _lookup_fast_info(fast_info: object, key: str) -> object:
        if fast_info is None:
            return None
        if isinstance(fast_info, dict):
            return fast_info.get(key)
        return getattr(fast_info, key, None)

    @staticmethod
    def _coerce_float(value: object) -> float | None:
        if value in (None, "", "None"):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if not np.isfinite(number):
            return None
        return number

    @staticmethod
    def _coerce_datetime(value: object) -> datetime | None:
        if value in (None, "", "None"):
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        try:
            ts = pd.Timestamp(value)
        except (TypeError, ValueError):
            return None
        if ts.tzinfo is not None:
            ts = ts.tz_convert("UTC").tz_localize(None)
        return ts.to_pydatetime()

    @classmethod
    def _compute_volume_ratio(cls, window: pd.DataFrame) -> float:
        volumes = pd.to_numeric(window["Volume"], errors="coerce").dropna()
        if volumes.empty:
            return 1.0
        if len(volumes) == 1:
            baseline = float(volumes.iloc[0])
        else:
            baseline = float(volumes.iloc[:-1].mean())
        latest = float(volumes.iloc[-1])
        if baseline <= 0:
            return 1.0
        return float(np.clip(latest / baseline, 0.1, 5.0))

    @classmethod
    def _compute_buy_sell_ratio(cls, window: pd.DataFrame) -> float:
        work = window.copy()
        price_delta = pd.to_numeric(work["Close"], errors="coerce") - pd.to_numeric(work["Open"], errors="coerce")
        if price_delta.abs().sum() == 0:
            price_delta = pd.to_numeric(work["Close"], errors="coerce").diff().fillna(0.0)

        volume = pd.to_numeric(work["Volume"], errors="coerce").fillna(0.0)
        buy_volume = float(volume[price_delta >= 0].sum())
        sell_volume = float(volume[price_delta < 0].sum())
        if buy_volume <= 0 and sell_volume <= 0:
            return 1.0
        if sell_volume <= 0:
            return 5.0
        return float(np.clip(buy_volume / sell_volume, 0.2, 5.0))

    @staticmethod
    def _ratio_to_signal(ratio: float) -> float:
        if ratio <= 0:
            return 0.0
        return float(np.clip(np.tanh(np.log(ratio)), -1.0, 1.0))

    @staticmethod
    def _volume_ratio_to_signal(volume_ratio: float) -> float:
        return float(np.clip(np.tanh(volume_ratio - 1.0), -1.0, 1.0))

    @staticmethod
    def _spread_pct_to_penalty(spread_pct: float) -> float:
        if spread_pct <= 0:
            return 0.0
        return float(np.clip(spread_pct / 0.01, 0.0, 1.0))

    def _empty_snapshot(self, quote_snapshot: dict[str, float | None]) -> MarketSignalSnapshot:
        return MarketSignalSnapshot(
            bid=quote_snapshot["bid"],
            ask=quote_snapshot["ask"],
            bid_ask_spread=quote_snapshot["bid_ask_spread"],
            spread_pct=quote_snapshot["spread_pct"],
            volume_ratio=1.0,
            buy_sell_ratio=1.0,
            buy_pressure=0.0,
            market_signal=0.0,
            last_price=self._coerce_float(quote_snapshot.get("last_price")),
            price_timestamp=self._coerce_datetime(quote_snapshot.get("price_timestamp")),
        )
