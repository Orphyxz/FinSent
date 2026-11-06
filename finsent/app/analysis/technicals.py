"""Technical indicators computed from daily OHLCV bars.

All functions are pure and take a frame with ``open``/``high``/``low``/``close``/``volume``
columns (case-insensitive) indexed or ordered by time. Nothing here reads providers.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd


TRADING_DAYS_PER_YEAR = 252


def normalize_ohlcv(frame: pd.DataFrame | None) -> pd.DataFrame:
    """Return a time-sorted frame with lowercase OHLCV columns and a ``timestamp`` column."""
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
    work = frame.copy()
    work.columns = [str(column).lower() for column in work.columns]
    if "timestamp" not in work.columns:
        work = work.reset_index().rename(columns={"index": "timestamp"})
        work.columns = [str(column).lower() for column in work.columns]
    work["timestamp"] = pd.to_datetime(work["timestamp"], errors="coerce")
    for column in ("open", "high", "low", "close", "volume"):
        work[column] = pd.to_numeric(work.get(column), errors="coerce")
    work = work.dropna(subset=["timestamp", "close"]).sort_values("timestamp")
    return work.drop_duplicates("timestamp", keep="last").reset_index(drop=True)[["timestamp", "open", "high", "low", "close", "volume"]]


def sma(close: pd.Series, window: int) -> pd.Series:
    return close.rolling(window, min_periods=window).mean()


def ema(close: pd.Series, span: int) -> pd.Series:
    return close.ewm(span=span, adjust=False, min_periods=span).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    result = 100.0 - (100.0 / (1.0 + rs))
    # No losses in the window means maximal strength rather than undefined.
    return result.where(avg_loss != 0.0, 100.0).where(avg_gain.notna())


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return pd.DataFrame({"macd": macd_line, "signal": signal_line, "histogram": macd_line - signal_line})


def bollinger(close: pd.Series, window: int = 20, width: float = 2.0) -> pd.DataFrame:
    middle = sma(close, window)
    std = close.rolling(window, min_periods=window).std()
    return pd.DataFrame({"middle": middle, "upper": middle + width * std, "lower": middle - width * std})


def annualized_volatility(close: pd.Series, window: int | None = None) -> float | None:
    returns = close.pct_change().dropna()
    if window is not None:
        returns = returns.tail(window)
    if len(returns) < 5:
        return None
    return float(returns.std() * math.sqrt(TRADING_DAYS_PER_YEAR))


def period_return(close: pd.Series, bars: int) -> float | None:
    clean = close.dropna()
    if len(clean) <= bars or bars <= 0:
        return None
    start = float(clean.iloc[-bars - 1])
    return None if start == 0 else float(clean.iloc[-1] / start - 1.0)


@dataclass(frozen=True, slots=True)
class TechnicalSnapshot:
    last_close: float | None
    rsi_14: float | None
    rsi_zone: str
    macd: float | None
    macd_signal: float | None
    macd_state: str
    sma_20: float | None
    sma_50: float | None
    sma_200: float | None
    trend: str
    high_52w: float | None
    low_52w: float | None
    volatility_30d: float | None
    return_1w: float | None
    return_1m: float | None
    return_3m: float | None
    return_1y: float | None
    avg_volume_20d: float | None
    bars: int


def _last(series: pd.Series) -> float | None:
    clean = series.dropna()
    return None if clean.empty else float(clean.iloc[-1])


def technical_snapshot(frame: pd.DataFrame | None) -> TechnicalSnapshot:
    bars = normalize_ohlcv(frame)
    close = bars["close"]
    rsi_value = _last(rsi(close))
    macd_frame = macd(close)
    macd_value = _last(macd_frame["macd"])
    signal_value = _last(macd_frame["signal"])
    sma_20, sma_50, sma_200 = (_last(sma(close, window)) for window in (20, 50, 200))
    last_close = _last(close)

    if rsi_value is None:
        rsi_zone = "Insufficient data"
    elif rsi_value >= 70:
        rsi_zone = "Overbought"
    elif rsi_value <= 30:
        rsi_zone = "Oversold"
    else:
        rsi_zone = "Neutral"

    if macd_value is None or signal_value is None:
        macd_state = "Insufficient data"
    else:
        histogram = macd_frame["histogram"].dropna()
        crossed = len(histogram) >= 2 and np.sign(histogram.iloc[-1]) != np.sign(histogram.iloc[-2])
        direction = "Bullish" if macd_value > signal_value else "Bearish"
        macd_state = f"{direction} crossover" if crossed else f"{direction} momentum"

    if last_close is None or sma_50 is None:
        trend = "Insufficient data"
    elif sma_200 is not None:
        if last_close > sma_50 > sma_200:
            trend = "Uptrend"
        elif last_close < sma_50 < sma_200:
            trend = "Downtrend"
        else:
            trend = "Mixed"
    else:
        trend = "Above 50-day" if last_close > sma_50 else "Below 50-day"

    year = bars.tail(TRADING_DAYS_PER_YEAR)
    return TechnicalSnapshot(
        last_close=last_close,
        rsi_14=rsi_value,
        rsi_zone=rsi_zone,
        macd=macd_value,
        macd_signal=signal_value,
        macd_state=macd_state,
        sma_20=sma_20,
        sma_50=sma_50,
        sma_200=sma_200,
        trend=trend,
        high_52w=None if year.empty else float(year["high"].max()),
        low_52w=None if year.empty else float(year["low"].min()),
        volatility_30d=annualized_volatility(close, 30),
        return_1w=period_return(close, 5),
        return_1m=period_return(close, 21),
        return_3m=period_return(close, 63),
        return_1y=period_return(close, 251),
        avg_volume_20d=_last(sma(bars["volume"], 20)),
        bars=len(bars),
    )


@dataclass(frozen=True, slots=True)
class RiskStats:
    annual_return: float | None
    annual_volatility: float | None
    sharpe: float | None
    sortino: float | None
    max_drawdown: float | None
    best_day: float | None
    worst_day: float | None
    up_day_ratio: float | None
    observations: int


def risk_stats(frame: pd.DataFrame | None, *, window: int = TRADING_DAYS_PER_YEAR) -> RiskStats:
    """Daily-return risk statistics over the last ``window`` bars (risk-free rate of zero)."""
    close = normalize_ohlcv(frame)["close"].tail(window + 1)
    returns = close.pct_change().dropna()
    if len(returns) < 20:
        return RiskStats(None, None, None, None, None, None, None, None, len(returns))
    root = math.sqrt(TRADING_DAYS_PER_YEAR)
    mean, std = float(returns.mean()), float(returns.std())
    downside = float(np.sqrt((returns.clip(upper=0.0) ** 2).mean()))
    drawdown = close / close.cummax() - 1.0
    return RiskStats(
        annual_return=float((1.0 + returns).prod() ** (TRADING_DAYS_PER_YEAR / len(returns)) - 1.0),
        annual_volatility=std * root,
        sharpe=mean / std * root if std else None,
        sortino=mean / downside * root if downside else None,
        max_drawdown=float(drawdown.min()),
        best_day=float(returns.max()),
        worst_day=float(returns.min()),
        up_day_ratio=float((returns > 0).mean()),
        observations=len(returns),
    )


def rolling_beta(stock: pd.Series, benchmark: pd.Series, window: int = 60) -> pd.Series:
    """Rolling beta of daily returns; both series must share one index."""
    covariance = stock.rolling(window, min_periods=window).cov(benchmark)
    variance = benchmark.rolling(window, min_periods=window).var()
    return covariance / variance.replace(0.0, np.nan)
