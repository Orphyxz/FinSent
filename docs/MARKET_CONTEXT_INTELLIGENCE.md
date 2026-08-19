# Market Context Intelligence

## Purpose

Market Context Intelligence adds benchmark, sector-relative, volatility, correlation, beta, and regime context to the live FinSent dashboard. It explains whether a selected stock is moving with the market, with its sector, or showing relative strength/weakness.

Market Context Intelligence is an application-level explanatory feature. Phase 19 does not establish additional predictive performance and does not modify the locked Phase 16 evaluation or Signal V1/V2 methodology.

## Benchmark Universe

Broad US benchmarks:

- SPY: S&P 500 proxy
- QQQ: Nasdaq-100 / growth-tech proxy
- DIA: Dow proxy
- IWM: Russell 2000 / small-cap proxy

SPY and QQQ are fetched for the application context path. DIA and IWM are documented as supported benchmark symbols for extension where provider/data constraints allow.

## Sector ETF Mapping

Sector ETFs:

- XLK: Technology
- XLY: Consumer Discretionary
- XLF: Financials
- XLC: Communication Services
- XLI: Industrials
- XLV: Health Care
- XLE: Energy
- XLP: Consumer Staples
- XLU: Utilities
- XLB: Materials
- XLRE: Real Estate

Curated demo-symbol mapping:

- AAPL, MSFT, NVDA -> XLK
- AMZN, TSLA -> XLY
- META, GOOGL -> XLC
- JPM -> XLF

For non-US symbols, Phase 19 returns a clear unsupported state rather than comparing NSE/BSE instruments to US ETFs.

## Formulas

Stock return:

```text
stock_return = last_close / first_close - 1
```

Market-relative return:

```text
market_relative_return = stock_return - benchmark_return
```

Sector-relative return:

```text
sector_relative_return = stock_return - sector_return
```

The UI shows these as percentage-point differences. It does not call them alpha.

## Relative Strength

Application thresholds:

- >= +1.5 percentage points: STRONG_RELATIVE_STRENGTH
- >= +0.5 percentage points: RELATIVE_STRENGTH
- between -0.5 and +0.5 percentage points: IN_LINE
- <= -0.5 percentage points: RELATIVE_WEAKNESS
- <= -1.5 percentage points: STRONG_RELATIVE_WEAKNESS

These thresholds are dashboard heuristics, not research-tuned thresholds.

## Volatility

Volatility is the standard deviation of aligned bar-to-bar returns over the available recent window. It is not annualized because the live dashboard may mix intraday and recent historical bars.

Volatility labels compare stock volatility to benchmark volatility:

- ratio <= 0.65: LOW
- ratio < 1.35: NORMAL
- ratio >= 1.35: ELEVATED
- ratio >= 2.0: HIGH

## Correlation

Correlation is rolling Pearson correlation over aligned returns. The implementation aligns timestamps, requires a minimum number of observations, and never correlates price levels.

Labels:

- HIGH_POSITIVE
- MODERATE_POSITIVE
- LOW
- NEGATIVE
- INSUFFICIENT_DATA

## Beta

Beta is descriptive historical beta over aligned returns:

```text
beta = covariance(stock_returns, market_returns) / variance(market_returns)
```

If there are too few observations or benchmark variance is zero, beta is not reported.

## Market Regime

The deterministic regime classifier uses SPY return, QQQ return, and SPY volatility.

Primary labels:

- RISK_ON
- RISK_OFF
- BULLISH
- BEARISH
- MIXED
- HIGH_VOLATILITY
- QUIET
- UNKNOWN

This is not an ML regime classifier.

## Freshness And Quality

Each context result includes provider, feed, latest timestamp, freshness, and quality.

Quality states:

- GOOD: stock, SPY, and sector data sufficient
- PARTIAL: stock and SPY available but sector missing
- INSUFFICIENT: some data exists but not enough for full calculations
- UNAVAILABLE: no usable context data

When the US market is closed, the UI uses latest-available wording rather than labeling context as live.

## Caching

Benchmark and sector ETF bars are fetched once per unique symbol per TTL window. Multiple Technology stocks reuse XLK. Multiple symbols reuse SPY and QQQ. This prevents N+1 benchmark requests during dashboard refreshes.

## UI Integration

Phase 19 integrates into:

- Overview: broad market context and compact vs-SPY/vs-sector rows
- Stock Research: Market Context panel and normalized relative performance chart
- Compare: relative-strength ranking, market/sector relative bars, volatility, correlation, beta, catalyst context

Catalyst Intelligence remains independent. Market context does not merge catalyst output into a synthetic score.

## Failure Behavior

If SPY fails, stock pages still render with a market-benchmark-unavailable warning. If a sector ETF fails, sector-relative fields are unavailable while stock and market context continue. Non-US instruments report that benchmark context is not configured for the market.

## Limitations

This phase is designed for US live/demo symbols. NSE/BSE benchmark support is future work and should use local market benchmarks such as NIFTY 50, SENSEX, and Indian sector indices.

Market Context Intelligence is explanatory context only. It does not change Signal V1, Signal V2, V2.1, or any locked Phase 16 research artifacts.
