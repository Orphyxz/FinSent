from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from threading import RLock
from typing import Callable, Iterable

import numpy as np
import pandas as pd

from finsent.app.config.settings import settings
from finsent.app.services.market_providers import classify_us_market_status
from finsent.app.services.provider_routers import MarketDataRouter
from finsent.app.services.runtime_diagnostics import CacheStats, runtime_diagnostics
from finsent.app.services.symbol_registry import SymbolRecord, registry


BROAD_MARKET_BENCHMARKS = {
    "SPY": "S&P 500 proxy",
    "QQQ": "Nasdaq-100 / growth-tech proxy",
    "DIA": "Dow proxy",
    "IWM": "Russell 2000 / small-cap proxy",
}

SECTOR_ETFS = {
    "XLK": "Technology",
    "XLY": "Consumer Discretionary",
    "XLF": "Financials",
    "XLC": "Communication Services",
    "XLI": "Industrials",
    "XLV": "Health Care",
    "XLE": "Energy",
    "XLP": "Consumer Staples",
    "XLU": "Utilities",
    "XLB": "Materials",
    "XLRE": "Real Estate",
}

CURATED_US_SECTOR_ETF_MAP = {
    "AAPL": "XLK",
    "MSFT": "XLK",
    "NVDA": "XLK",
    "AMZN": "XLY",
    "TSLA": "XLY",
    "META": "XLC",
    "GOOGL": "XLC",
    "JPM": "XLF",
}

SECTOR_NAME_TO_ETF = {
    "technology": "XLK",
    "consumer": "XLY",
    "consumer discretionary": "XLY",
    "finance": "XLF",
    "financials": "XLF",
    "communication services": "XLC",
    "communications": "XLC",
    "industrials": "XLI",
    "health care": "XLV",
    "healthcare": "XLV",
    "energy": "XLE",
    "consumer staples": "XLP",
    "utilities": "XLU",
    "materials": "XLB",
    "real estate": "XLRE",
}


class RelativeStrengthLabel(str, Enum):
    STRONG_RELATIVE_STRENGTH = "STRONG_RELATIVE_STRENGTH"
    RELATIVE_STRENGTH = "RELATIVE_STRENGTH"
    IN_LINE = "IN_LINE"
    RELATIVE_WEAKNESS = "RELATIVE_WEAKNESS"
    STRONG_RELATIVE_WEAKNESS = "STRONG_RELATIVE_WEAKNESS"
    UNKNOWN = "UNKNOWN"


class MoveAttributionLabel(str, Enum):
    STOCK_SPECIFIC_STRENGTH = "STOCK_SPECIFIC_STRENGTH"
    STOCK_SPECIFIC_WEAKNESS = "STOCK_SPECIFIC_WEAKNESS"
    MARKET_LED_STRENGTH = "MARKET_LED_STRENGTH"
    MARKET_LED_WEAKNESS = "MARKET_LED_WEAKNESS"
    SECTOR_LED_MOVE = "SECTOR_LED_MOVE"
    RELATIVE_RESILIENCE = "RELATIVE_RESILIENCE"
    MIXED = "MIXED"
    IN_LINE = "IN_LINE"
    UNKNOWN = "UNKNOWN"


class VolatilityLabel(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


class CorrelationLabel(str, Enum):
    HIGH_POSITIVE = "HIGH_POSITIVE"
    MODERATE_POSITIVE = "MODERATE_POSITIVE"
    LOW = "LOW"
    NEGATIVE = "NEGATIVE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class MarketRegime(str, Enum):
    RISK_ON = "RISK_ON"
    RISK_OFF = "RISK_OFF"
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    MIXED = "MIXED"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    QUIET = "QUIET"
    UNKNOWN = "UNKNOWN"


class MarketContextQuality(str, Enum):
    GOOD = "GOOD"
    PARTIAL = "PARTIAL"
    INSUFFICIENT = "INSUFFICIENT"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class MarketContextResult:
    symbol: str
    benchmark_symbol: str | None
    sector_benchmark_symbol: str | None
    stock_return: float | None
    benchmark_return: float | None
    sector_return: float | None
    qqq_return: float | None
    market_relative_return: float | None
    sector_relative_return: float | None
    relative_strength_label: RelativeStrengthLabel
    stock_volatility: float | None
    benchmark_volatility: float | None
    sector_volatility: float | None
    volatility_ratio: float | None
    volatility_label: VolatilityLabel
    correlation_to_market: float | None
    correlation_to_sector: float | None
    correlation_label: CorrelationLabel
    beta_to_market: float | None
    market_regime: MarketRegime
    sector_regime: MarketRegime
    stock_move_context: MoveAttributionLabel
    data_start: datetime | None
    data_end: datetime | None
    bar_count: int
    provider: str
    feed: str | None
    freshness: str
    latest_timestamp: datetime | None
    retrieved_at: datetime
    quality: MarketContextQuality
    warnings: tuple[str, ...]


@dataclass(slots=True)
class _BarsEntry:
    frame: pd.DataFrame
    provider: str
    feed: str | None
    freshness: str
    latest_timestamp: datetime | None
    retrieved_at: datetime


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def sector_etf_for_symbol(symbol: SymbolRecord | str | None) -> str | None:
    if symbol is None:
        return None
    if isinstance(symbol, str):
        resolved = registry.resolve_any(symbol)
        ticker = symbol.upper().strip()
        sector = resolved.sector if resolved is not None else ""
    else:
        resolved = symbol
        ticker = symbol.ticker.upper().strip()
        sector = symbol.sector
    if resolved is not None and resolved.exchange != "US":
        return None
    if ticker in CURATED_US_SECTOR_ETF_MAP:
        return CURATED_US_SECTOR_ETF_MAP[ticker]
    return SECTOR_NAME_TO_ETF.get(str(sector or "").strip().lower())


def benchmark_symbol_record(ticker: str) -> SymbolRecord:
    normalized = ticker.upper().strip()
    label_source = BROAD_MARKET_BENCHMARKS.get(normalized) or SECTOR_ETFS.get(normalized) or "US benchmark"
    return SymbolRecord(
        internal_id=f"us-benchmark-{normalized.lower()}",
        ticker=normalized,
        display_name=label_source,
        exchange="US",
        provider_symbol=normalized,
        ui_label=f"{normalized} | {label_source} | US",
        sector="Benchmark",
        polygon_symbol=normalized,
    )


def normalize_bars(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["timestamp", "close"])
    work = frame.copy()
    if "timestamp" in work.columns:
        timestamps = pd.to_datetime(work["timestamp"], errors="coerce")
    else:
        timestamps = pd.to_datetime(work.index, errors="coerce")
    close_col = "Close" if "Close" in work.columns else "close" if "close" in work.columns else None
    if close_col is None:
        return pd.DataFrame(columns=["timestamp", "close"])
    result = pd.DataFrame(
        {
            "timestamp": timestamps,
            "close": pd.to_numeric(work[close_col], errors="coerce"),
        }
    ).reset_index(drop=True)
    result = result.dropna(subset=["timestamp", "close"])
    result = result[result["close"] > 0]
    if result.empty:
        return pd.DataFrame(columns=["timestamp", "close"])
    result["timestamp"] = result["timestamp"].dt.tz_localize(None) if getattr(result["timestamp"].dt, "tz", None) is not None else result["timestamp"]
    return result.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last").reset_index(drop=True)


def window_return(frame: pd.DataFrame | None) -> float | None:
    work = normalize_bars(frame)
    if len(work) < 2:
        return None
    first = float(work["close"].iloc[0])
    last = float(work["close"].iloc[-1])
    if first <= 0:
        return None
    return (last - first) / first


def align_bars_to_common_window(
    left: pd.DataFrame | None,
    right: pd.DataFrame | None,
    *,
    minimum_bars: int = 2,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    left_work = normalize_bars(left)
    right_work = normalize_bars(right)
    if left_work.empty or right_work.empty:
        return pd.DataFrame(columns=["timestamp", "close"]), pd.DataFrame(columns=["timestamp", "close"])
    left_indexed = left_work.set_index("timestamp")
    right_indexed = right_work.set_index("timestamp")
    common_index = left_indexed.index.intersection(right_indexed.index).sort_values()
    if len(common_index) < minimum_bars:
        return pd.DataFrame(columns=["timestamp", "close"]), pd.DataFrame(columns=["timestamp", "close"])
    return (
        left_indexed.loc[common_index].reset_index(),
        right_indexed.loc[common_index].reset_index(),
    )


def aligned_window_returns(
    left: pd.DataFrame | None,
    right: pd.DataFrame | None,
    *,
    minimum_bars: int = 2,
) -> tuple[float | None, float | None, int]:
    left_aligned, right_aligned = align_bars_to_common_window(left, right, minimum_bars=minimum_bars)
    if left_aligned.empty or right_aligned.empty:
        return None, None, 0
    return window_return(left_aligned), window_return(right_aligned), int(len(left_aligned))


def bar_returns(frame: pd.DataFrame | None) -> pd.Series:
    work = normalize_bars(frame)
    if len(work) < 2:
        return pd.Series(dtype=float)
    returns = work.set_index("timestamp")["close"].pct_change().dropna()
    return returns.replace([np.inf, -np.inf], np.nan).dropna()


def realized_volatility(frame: pd.DataFrame | None) -> float | None:
    returns = bar_returns(frame)
    if len(returns) < 2:
        return None
    return float(returns.std(ddof=1))


def aligned_returns(left: pd.DataFrame | None, right: pd.DataFrame | None) -> pd.DataFrame:
    left_frame, right_frame = align_bars_to_common_window(left, right, minimum_bars=2)
    left_returns = bar_returns(left_frame).rename("left")
    right_returns = bar_returns(right_frame).rename("right")
    if left_returns.empty or right_returns.empty:
        return pd.DataFrame(columns=["left", "right"])
    joined = pd.concat([left_returns, right_returns], axis=1, join="inner").dropna()
    return joined.reset_index(drop=False)


def return_correlation(left: pd.DataFrame | None, right: pd.DataFrame | None, minimum_observations: int = 3) -> float | None:
    joined = aligned_returns(left, right)
    if len(joined) < minimum_observations:
        return None
    corr = joined["left"].corr(joined["right"])
    return float(corr) if pd.notna(corr) else None


def historical_beta(left: pd.DataFrame | None, right: pd.DataFrame | None, minimum_observations: int = 3) -> float | None:
    joined = aligned_returns(left, right)
    if len(joined) < minimum_observations:
        return None
    market_var = float(joined["right"].var(ddof=1))
    if market_var == 0 or not np.isfinite(market_var):
        return None
    covariance = float(joined["left"].cov(joined["right"]))
    return covariance / market_var


def relative_return(stock_return: float | None, benchmark_return: float | None) -> float | None:
    if stock_return is None or benchmark_return is None:
        return None
    return stock_return - benchmark_return


def classify_relative_strength(value: float | None) -> RelativeStrengthLabel:
    if value is None:
        return RelativeStrengthLabel.UNKNOWN
    pct_points = value * 100.0
    if pct_points >= 1.5:
        return RelativeStrengthLabel.STRONG_RELATIVE_STRENGTH
    if pct_points >= 0.5:
        return RelativeStrengthLabel.RELATIVE_STRENGTH
    if pct_points <= -1.5:
        return RelativeStrengthLabel.STRONG_RELATIVE_WEAKNESS
    if pct_points <= -0.5:
        return RelativeStrengthLabel.RELATIVE_WEAKNESS
    return RelativeStrengthLabel.IN_LINE


def classify_volatility(stock_volatility: float | None, benchmark_volatility: float | None) -> tuple[VolatilityLabel, float | None]:
    if stock_volatility is None:
        return VolatilityLabel.UNKNOWN, None
    if benchmark_volatility is None or benchmark_volatility <= 0:
        if stock_volatility >= 0.025:
            return VolatilityLabel.HIGH, None
        if stock_volatility >= 0.012:
            return VolatilityLabel.ELEVATED, None
        return VolatilityLabel.NORMAL, None
    ratio = stock_volatility / benchmark_volatility
    if ratio >= 2.0:
        return VolatilityLabel.HIGH, float(ratio)
    if ratio >= 1.35:
        return VolatilityLabel.ELEVATED, float(ratio)
    if ratio <= 0.65:
        return VolatilityLabel.LOW, float(ratio)
    return VolatilityLabel.NORMAL, float(ratio)


def classify_correlation(correlation: float | None) -> CorrelationLabel:
    if correlation is None:
        return CorrelationLabel.INSUFFICIENT_DATA
    if correlation >= 0.70:
        return CorrelationLabel.HIGH_POSITIVE
    if correlation >= 0.35:
        return CorrelationLabel.MODERATE_POSITIVE
    if correlation < 0:
        return CorrelationLabel.NEGATIVE
    return CorrelationLabel.LOW


def classify_market_regime(
    spy_return: float | None,
    qqq_return: float | None,
    spy_volatility: float | None = None,
) -> MarketRegime:
    if spy_return is None and qqq_return is None:
        return MarketRegime.UNKNOWN
    if spy_volatility is not None and spy_volatility >= 0.02:
        return MarketRegime.HIGH_VOLATILITY
    spy = spy_return or 0.0
    qqq = qqq_return if qqq_return is not None else spy
    if spy >= 0.006 and qqq >= 0.006:
        return MarketRegime.RISK_ON if qqq >= spy else MarketRegime.BULLISH
    if spy <= -0.006 and qqq <= -0.006:
        return MarketRegime.RISK_OFF if qqq <= spy else MarketRegime.BEARISH
    if abs(spy) <= 0.002 and abs(qqq) <= 0.002 and (spy_volatility is None or spy_volatility < 0.006):
        return MarketRegime.QUIET
    if (spy >= 0 and qqq < 0) or (spy < 0 and qqq >= 0):
        return MarketRegime.MIXED
    return MarketRegime.BULLISH if spy > 0 else MarketRegime.BEARISH if spy < 0 else MarketRegime.MIXED


def classify_move_attribution(
    stock_return: float | None,
    market_return: float | None,
    sector_return: float | None,
) -> MoveAttributionLabel:
    if stock_return is None or market_return is None:
        return MoveAttributionLabel.UNKNOWN
    market_relative = relative_return(stock_return, market_return)
    sector_relative = relative_return(stock_return, sector_return)
    if market_relative is None:
        return MoveAttributionLabel.UNKNOWN
    if stock_return >= 0.01 and market_relative >= 0.01 and (sector_relative is None or sector_relative >= 0.005):
        return MoveAttributionLabel.STOCK_SPECIFIC_STRENGTH
    if stock_return <= -0.01 and market_relative <= -0.01 and (sector_relative is None or sector_relative <= -0.005):
        return MoveAttributionLabel.STOCK_SPECIFIC_WEAKNESS
    if stock_return > 0 and market_return > 0 and abs(market_relative) <= 0.005:
        return MoveAttributionLabel.MARKET_LED_STRENGTH
    if stock_return < 0 and market_return < 0 and abs(market_relative) <= 0.005:
        return MoveAttributionLabel.MARKET_LED_WEAKNESS
    if sector_relative is not None and abs(sector_relative) <= 0.005 and abs(market_relative) > 0.005:
        return MoveAttributionLabel.SECTOR_LED_MOVE
    if stock_return < 0 and market_return < stock_return and market_relative >= 0.01:
        return MoveAttributionLabel.RELATIVE_RESILIENCE
    if abs(market_relative) <= 0.005 and (sector_relative is None or abs(sector_relative) <= 0.005):
        return MoveAttributionLabel.IN_LINE
    return MoveAttributionLabel.MIXED


def market_context_results_to_frame(results: Iterable[MarketContextResult]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": result.symbol,
                "benchmark_symbol": result.benchmark_symbol,
                "sector_benchmark_symbol": result.sector_benchmark_symbol,
                "stock_return": result.stock_return,
                "benchmark_return": result.benchmark_return,
                "sector_return": result.sector_return,
                "qqq_return": result.qqq_return,
                "market_relative_return": result.market_relative_return,
                "sector_relative_return": result.sector_relative_return,
                "relative_strength_label": result.relative_strength_label.value,
                "stock_volatility": result.stock_volatility,
                "benchmark_volatility": result.benchmark_volatility,
                "sector_volatility": result.sector_volatility,
                "volatility_ratio": result.volatility_ratio,
                "volatility_label": result.volatility_label.value,
                "correlation_to_market": result.correlation_to_market,
                "correlation_to_sector": result.correlation_to_sector,
                "correlation_label": result.correlation_label.value,
                "beta_to_market": result.beta_to_market,
                "market_regime": result.market_regime.value,
                "sector_regime": result.sector_regime.value,
                "stock_move_context": result.stock_move_context.value,
                "data_start": result.data_start,
                "data_end": result.data_end,
                "bar_count": result.bar_count,
                "provider": result.provider,
                "feed": result.feed,
                "freshness": result.freshness,
                "latest_timestamp": result.latest_timestamp,
                "retrieved_at": result.retrieved_at,
                "quality": result.quality.value,
                "warnings": "; ".join(result.warnings),
            }
            for result in results
        ]
    )


class MarketContextService:
    def __init__(
        self,
        *,
        router: MarketDataRouter | None = None,
        clock: Callable[[], datetime] | None = None,
        ttl_seconds: int = 300,
    ) -> None:
        self.router = router or MarketDataRouter(clock=clock)
        self.clock = clock or utc_now
        self.ttl_seconds = ttl_seconds
        self._bars_cache: dict[tuple[str, str, str, str], _BarsEntry] = {}
        self._lock = RLock()
        self._cache_hits = 0
        self._cache_misses = 0
        self._expired = 0
        self.fetch_counts: dict[str, int] = {}

    def build_contexts(
        self,
        symbols: list[str],
        *,
        price_df: pd.DataFrame | None = None,
        lookback_days: int = 5,
        interval: str = "15m",
    ) -> list[MarketContextResult]:
        resolved = [registry.resolve_any(symbol) for symbol in symbols]
        symbol_records = [symbol for symbol in resolved if symbol is not None]
        end = self.clock()
        start = end - timedelta(days=lookback_days)
        benchmark_symbols = {"SPY", "QQQ"}
        sector_symbols = {sector_etf_for_symbol(symbol) for symbol in symbol_records if symbol.exchange == "US"}
        benchmark_symbols.update(symbol for symbol in sector_symbols if symbol)

        fetched: dict[str, _BarsEntry] = {
            ticker: self._fetch_bars(benchmark_symbol_record(ticker), start=start, end=end, interval=interval)
            for ticker in sorted(benchmark_symbols)
        }
        contexts: list[MarketContextResult] = []
        for symbol in symbol_records:
            if symbol.exchange != "US":
                contexts.append(self._unsupported_market(symbol))
                continue
            stock_frame = self._stock_frame_from_price_df(symbol.provider_symbol, price_df)
            if stock_frame.empty:
                stock_entry = self._fetch_bars(symbol, start=start, end=end, interval=interval)
                stock_frame = stock_entry.frame
                provider = stock_entry.provider
                feed = stock_entry.feed
                freshness = stock_entry.freshness
            else:
                provider = "stored_price_frame"
                feed = None
                freshness = _freshness_from_timestamp(_latest_timestamp(stock_frame), self.clock())
            sector_symbol = sector_etf_for_symbol(symbol)
            contexts.append(
                self._build_result(
                    symbol=symbol,
                    stock_frame=stock_frame,
                    benchmark_entry=fetched.get("SPY"),
                    qqq_entry=fetched.get("QQQ"),
                    sector_entry=fetched.get(sector_symbol or ""),
                    sector_symbol=sector_symbol,
                    provider=provider,
                    feed=feed,
                    freshness=freshness,
                )
            )
        return contexts

    def _build_result(
        self,
        *,
        symbol: SymbolRecord,
        stock_frame: pd.DataFrame,
        benchmark_entry: _BarsEntry | None,
        qqq_entry: _BarsEntry | None,
        sector_entry: _BarsEntry | None,
        sector_symbol: str | None,
        provider: str,
        feed: str | None,
        freshness: str,
    ) -> MarketContextResult:
        benchmark_frame = benchmark_entry.frame if benchmark_entry is not None else pd.DataFrame()
        qqq_frame = qqq_entry.frame if qqq_entry is not None else pd.DataFrame()
        sector_frame = sector_entry.frame if sector_entry is not None else pd.DataFrame()
        stock_benchmark_frame, aligned_benchmark_frame = align_bars_to_common_window(stock_frame, benchmark_frame)
        stock_sector_frame, aligned_sector_frame = align_bars_to_common_window(stock_frame, sector_frame)
        aligned_spy_for_regime, aligned_qqq_frame = align_bars_to_common_window(benchmark_frame, qqq_frame)
        stock_return, benchmark_return, market_overlap = aligned_window_returns(stock_frame, benchmark_frame)
        _stock_sector_return, sector_return, sector_overlap = aligned_window_returns(stock_frame, sector_frame)
        spy_regime_return = window_return(aligned_spy_for_regime) if not aligned_spy_for_regime.empty else benchmark_return
        qqq_return = window_return(aligned_qqq_frame) if not aligned_qqq_frame.empty else None
        market_relative = relative_return(stock_return, benchmark_return)
        sector_relative = relative_return(_stock_sector_return, sector_return)
        stock_vol = realized_volatility(stock_benchmark_frame)
        benchmark_vol = realized_volatility(aligned_benchmark_frame)
        sector_vol = realized_volatility(aligned_sector_frame)
        vol_label, vol_ratio = classify_volatility(stock_vol, benchmark_vol)
        corr_market = return_correlation(stock_benchmark_frame, aligned_benchmark_frame)
        corr_sector = return_correlation(stock_sector_frame, aligned_sector_frame)
        beta = historical_beta(stock_benchmark_frame, aligned_benchmark_frame)
        market_regime = classify_market_regime(spy_regime_return, qqq_return, benchmark_vol)
        sector_regime = classify_market_regime(sector_return, qqq_return, sector_vol) if sector_return is not None else MarketRegime.UNKNOWN
        quality, warnings = _quality_and_warnings(stock_return, benchmark_return, sector_return, corr_market, market_overlap=market_overlap, sector_overlap=sector_overlap)
        normalized = stock_benchmark_frame if not stock_benchmark_frame.empty else normalize_bars(stock_frame)
        latest = _latest_timestamp(normalized)
        return MarketContextResult(
            symbol=symbol.provider_symbol,
            benchmark_symbol="SPY",
            sector_benchmark_symbol=sector_symbol,
            stock_return=stock_return,
            benchmark_return=benchmark_return,
            sector_return=sector_return,
            qqq_return=qqq_return,
            market_relative_return=market_relative,
            sector_relative_return=sector_relative,
            relative_strength_label=classify_relative_strength(sector_relative if sector_relative is not None else market_relative),
            stock_volatility=stock_vol,
            benchmark_volatility=benchmark_vol,
            sector_volatility=sector_vol,
            volatility_ratio=vol_ratio,
            volatility_label=vol_label,
            correlation_to_market=corr_market,
            correlation_to_sector=corr_sector,
            correlation_label=classify_correlation(corr_market),
            beta_to_market=beta,
            market_regime=market_regime,
            sector_regime=sector_regime,
            stock_move_context=classify_move_attribution(stock_return, benchmark_return, sector_return),
            data_start=normalized["timestamp"].min().to_pydatetime() if not normalized.empty else None,
            data_end=normalized["timestamp"].max().to_pydatetime() if not normalized.empty else None,
            bar_count=int(len(normalized)),
            provider=provider if provider != "stored_price_frame" else (benchmark_entry.provider if benchmark_entry is not None else provider),
            feed=feed or (benchmark_entry.feed if benchmark_entry is not None else None),
            freshness=_context_freshness(freshness, benchmark_entry, sector_entry),
            latest_timestamp=latest,
            retrieved_at=self.clock(),
            quality=quality,
            warnings=tuple(warnings),
        )

    def _unsupported_market(self, symbol: SymbolRecord) -> MarketContextResult:
        now = self.clock()
        return MarketContextResult(
            symbol=symbol.provider_symbol,
            benchmark_symbol=None,
            sector_benchmark_symbol=None,
            stock_return=None,
            benchmark_return=None,
            sector_return=None,
            qqq_return=None,
            market_relative_return=None,
            sector_relative_return=None,
            relative_strength_label=RelativeStrengthLabel.UNKNOWN,
            stock_volatility=None,
            benchmark_volatility=None,
            sector_volatility=None,
            volatility_ratio=None,
            volatility_label=VolatilityLabel.UNKNOWN,
            correlation_to_market=None,
            correlation_to_sector=None,
            correlation_label=CorrelationLabel.INSUFFICIENT_DATA,
            beta_to_market=None,
            market_regime=MarketRegime.UNKNOWN,
            sector_regime=MarketRegime.UNKNOWN,
            stock_move_context=MoveAttributionLabel.UNKNOWN,
            data_start=None,
            data_end=None,
            bar_count=0,
            provider="unavailable",
            feed=None,
            freshness="UNAVAILABLE",
            latest_timestamp=None,
            retrieved_at=now,
            quality=MarketContextQuality.UNAVAILABLE,
            warnings=("Benchmark context not configured for this market.",),
        )

    def _fetch_bars(self, symbol: SymbolRecord, *, start: datetime, end: datetime, interval: str) -> _BarsEntry:
        cache_key = (symbol.provider_symbol, start.strftime("%Y%m%d"), end.strftime("%Y%m%d%H%M")[:11], interval)
        now = self.clock()
        with self._lock:
            cached = self._bars_cache.get(cache_key)
            if cached is not None and (now - cached.retrieved_at).total_seconds() <= self.ttl_seconds:
                self._cache_hits += 1
                self._publish_cache_stats()
                return cached
            if cached is not None:
                self._expired += 1
            self._cache_misses += 1
            self.fetch_counts[symbol.provider_symbol] = self.fetch_counts.get(symbol.provider_symbol, 0) + 1
            self._publish_cache_stats()
        result = self.router.fetch_price_bars(symbol, start=start, end=end, interval=interval)
        frame = normalize_bars(result.data)
        latest = _latest_timestamp(frame)
        entry = _BarsEntry(
            frame=frame,
            provider=result.provider,
            feed=_feed_label(result.provider),
            freshness=_freshness_from_timestamp(latest, now),
            latest_timestamp=latest,
            retrieved_at=now,
        )
        with self._lock:
            self._bars_cache[cache_key] = entry
            self._publish_cache_stats()
        return entry

    def _stock_frame_from_price_df(self, ticker: str, price_df: pd.DataFrame | None) -> pd.DataFrame:
        if price_df is None or price_df.empty or "ticker" not in price_df.columns:
            return pd.DataFrame(columns=["timestamp", "close"])
        subset = price_df[price_df["ticker"] == ticker]
        return normalize_bars(subset)

    def cached_bars(self, ticker: str) -> pd.DataFrame:
        normalized = ticker.upper().strip()
        with self._lock:
            matches = [
                entry
                for key, entry in self._bars_cache.items()
                if key[0] == normalized
            ]
        if not matches:
            return pd.DataFrame(columns=["timestamp", "close"])
        return max(matches, key=lambda entry: entry.retrieved_at).frame.copy()

    def cache_stats(self) -> CacheStats:
        with self._lock:
            return CacheStats(
                name="market_context_bars",
                hits=self._cache_hits,
                misses=self._cache_misses,
                expired=self._expired,
                entries=len(self._bars_cache),
            )

    def _publish_cache_stats(self) -> None:
        runtime_diagnostics.record_cache_stats(self.cache_stats())


def _quality_and_warnings(
    stock_return: float | None,
    benchmark_return: float | None,
    sector_return: float | None,
    correlation_to_market: float | None,
    *,
    market_overlap: int | None = None,
    sector_overlap: int | None = None,
) -> tuple[MarketContextQuality, list[str]]:
    warnings: list[str] = []
    if stock_return is None:
        warnings.append("Stock/benchmark overlap unavailable or insufficient.")
    if benchmark_return is None:
        warnings.append("Market benchmark unavailable.")
    if sector_return is None:
        warnings.append("Sector benchmark unavailable.")
    if correlation_to_market is None:
        warnings.append("Insufficient aligned returns for correlation/beta.")
    if market_overlap is not None and 0 < market_overlap < 4:
        warnings.append("Market-relative window has limited overlap.")
    if sector_overlap is not None and 0 < sector_overlap < 4:
        warnings.append("Sector-relative window has limited overlap.")
    if stock_return is not None and benchmark_return is not None and sector_return is not None:
        return (MarketContextQuality.GOOD if correlation_to_market is not None else MarketContextQuality.INSUFFICIENT), warnings
    if stock_return is not None and benchmark_return is not None:
        return MarketContextQuality.PARTIAL, warnings
    if stock_return is not None or benchmark_return is not None or sector_return is not None:
        return MarketContextQuality.INSUFFICIENT, warnings
    return MarketContextQuality.UNAVAILABLE, warnings


def _freshness_from_timestamp(latest: datetime | None, now: datetime) -> str:
    if latest is None:
        return "UNAVAILABLE"
    market_status = classify_us_market_status(now.replace(tzinfo=timezone.utc))
    if market_status != "MARKET OPEN":
        return "LATEST AVAILABLE MARKET CONTEXT"
    age_seconds = (now - latest).total_seconds()
    if age_seconds <= 300:
        return "LIVE"
    if age_seconds <= 3600:
        return "DELAYED"
    return "STALE"


def _context_freshness(stock_freshness: str, benchmark_entry: _BarsEntry | None, sector_entry: _BarsEntry | None) -> str:
    values = [stock_freshness]
    if benchmark_entry is not None:
        values.append(benchmark_entry.freshness)
    if sector_entry is not None:
        values.append(sector_entry.freshness)
    if any(value == "UNAVAILABLE" for value in values):
        return "PARTIAL"
    if any(value == "LATEST AVAILABLE MARKET CONTEXT" for value in values):
        return "LATEST AVAILABLE MARKET CONTEXT"
    if any(value == "STALE" for value in values):
        return "STALE"
    if any(value == "DELAYED" for value in values):
        return "DELAYED"
    return "LIVE"


def _latest_timestamp(frame: pd.DataFrame | None) -> datetime | None:
    work = normalize_bars(frame)
    if work.empty:
        return None
    return pd.to_datetime(work["timestamp"], errors="coerce").max().to_pydatetime()


def _feed_label(provider: str) -> str:
    if provider == "alpaca":
        return (settings.alpaca_feed or "iex").strip().lower() or "iex"
    return provider


market_context_service = MarketContextService()
