"""Daily benchmark statistics for any supported stock, US or Indian.

US stocks are measured against SPY and their mapped sector ETF; NSE/BSE stocks against
NIFTY 50 and the closest NSE sector index. Everything uses daily closes aligned on
common trading days, so beta and correlation are comparable across markets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math

import numpy as np
import pandas as pd

from finsent.app.analysis.technicals import TRADING_DAYS_PER_YEAR, rolling_beta
from finsent.app.services import market_overview
from finsent.app.services.market_context import sector_etf_for_symbol
from finsent.app.services.symbol_registry import registry


INDIA_MARKET_INDEX = ("^NSEI", "NIFTY 50")
INDIA_SECTOR_INDEX = {
    "Technology": ("^CNXIT", "NIFTY IT"),
    "Financials": ("NIFTY_FIN_SERVICE.NS", "NIFTY Financial Services"),
    "Consumer Discretionary": ("^CNXAUTO", "NIFTY Auto"),
    "Health Care": ("^CNXPHARMA", "NIFTY Pharma"),
    "Consumer Staples": ("^CNXFMCG", "NIFTY FMCG"),
    "Materials": ("^CNXMETAL", "NIFTY Metal"),
    "Energy": ("^CNXENERGY", "NIFTY Energy"),
    "Utilities": ("^CNXENERGY", "NIFTY Energy"),
    "Real Estate": ("^CNXREALTY", "NIFTY Realty"),
    "Industrials": ("^CNXINFRA", "NIFTY Infrastructure"),
}
BETA_WINDOW = 126


@dataclass(slots=True)
class BenchmarkStats:
    ticker: str
    market_label: str
    sector_label: str | None
    beta: float | None
    correlation: float | None
    excess_1m: float | None
    excess_3m: float | None
    sector_excess_3m: float | None
    volatility_ratio: float | None
    series: dict[str, pd.DataFrame] = field(default_factory=dict)

    @property
    def available(self) -> bool:
        return self.beta is not None


def _benchmark_frames(ticker: str) -> tuple[tuple[str, pd.DataFrame], tuple[str, pd.DataFrame] | None]:
    symbol = registry.resolve_any(ticker)
    if symbol is not None and symbol.exchange in {"NSE", "BSE"}:
        market = (INDIA_MARKET_INDEX[1], market_overview.yahoo_index_history(INDIA_MARKET_INDEX[0], range_="1y"))
        sector_index = INDIA_SECTOR_INDEX.get(symbol.sector)
        sector = (sector_index[1], market_overview.yahoo_index_history(sector_index[0], range_="1y")) if sector_index else None
        return market, sector
    market = ("S&P 500 (SPY)", market_overview.daily_history("SPY"))
    etf = sector_etf_for_symbol(symbol or ticker)
    sector = (f"Sector ETF ({etf})", market_overview.daily_history(etf)) if etf else None
    return market, sector


def _aligned_returns(stock: pd.DataFrame, bench: pd.DataFrame) -> pd.DataFrame:
    left = stock.assign(day=stock["timestamp"].dt.normalize()).groupby("day")["close"].last()
    right = bench.assign(day=bench["timestamp"].dt.normalize()).groupby("day")["close"].last()
    joined = pd.concat({"stock": left, "bench": right}, axis=1).dropna()
    return joined.pct_change().dropna()


def _excess(stock: pd.DataFrame, bench: pd.DataFrame, bars: int) -> float | None:
    joined = pd.concat(
        {
            "stock": stock.assign(day=stock["timestamp"].dt.normalize()).groupby("day")["close"].last(),
            "bench": bench.assign(day=bench["timestamp"].dt.normalize()).groupby("day")["close"].last(),
        },
        axis=1,
    ).dropna()
    if len(joined) <= bars:
        return None
    window = joined.tail(bars + 1)
    stock_return = window["stock"].iloc[-1] / window["stock"].iloc[0] - 1.0
    bench_return = window["bench"].iloc[-1] / window["bench"].iloc[0] - 1.0
    return float(stock_return - bench_return)


def benchmark_stats(ticker: str) -> BenchmarkStats:
    stock = market_overview.daily_history(ticker)
    (market_label, market), sector = _benchmark_frames(ticker)
    if stock.empty or market.empty:
        return BenchmarkStats(ticker, market_label, sector[0] if sector else None, None, None, None, None, None, None)
    returns = _aligned_returns(stock, market).tail(BETA_WINDOW)
    beta = correlation = vol_ratio = None
    if len(returns) >= 30 and returns["bench"].var() > 0:
        beta = float(returns["stock"].cov(returns["bench"]) / returns["bench"].var())
        correlation = float(returns["stock"].corr(returns["bench"]))
        bench_vol = returns["bench"].std() * math.sqrt(TRADING_DAYS_PER_YEAR)
        vol_ratio = float(returns["stock"].std() * math.sqrt(TRADING_DAYS_PER_YEAR) / bench_vol) if bench_vol else None
    sector_frame = sector[1] if sector else pd.DataFrame()
    series = {ticker: stock.tail(BETA_WINDOW), market_label: market.tail(BETA_WINDOW)}
    if sector and not sector_frame.empty:
        series[sector[0]] = sector_frame.tail(BETA_WINDOW)
    return BenchmarkStats(
        ticker=ticker,
        market_label=market_label,
        sector_label=sector[0] if sector else None,
        beta=None if beta is None or not np.isfinite(beta) else beta,
        correlation=correlation,
        excess_1m=_excess(stock, market, 21),
        excess_3m=_excess(stock, market, 63),
        sector_excess_3m=_excess(stock, sector_frame, 63) if sector and not sector_frame.empty else None,
        volatility_ratio=vol_ratio,
        series=series,
    )


def rolling_beta_series(ticker: str, window: int = 60) -> tuple[pd.Series, pd.Series, str]:
    """Rolling beta against the stock's market benchmark: (dates, beta, benchmark label)."""
    stock = market_overview.daily_history(ticker)
    (label, market), _sector = _benchmark_frames(ticker)
    if stock.empty or market.empty:
        return pd.Series(dtype="datetime64[ns]"), pd.Series(dtype=float), label
    returns = _aligned_returns(stock, market)
    beta = rolling_beta(returns["stock"], returns["bench"], window)
    return pd.Series(returns.index, index=returns.index), beta, label
