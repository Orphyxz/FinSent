# Project Summary

## Problem

Financial news moves quickly, but raw headlines, quotes, and market context are difficult to interpret together. FinSent addresses this by combining current news sentiment, catalyst classification, market context, and explainable short-term signals inside one local research dashboard.

## Motivation

The goal is not to build an automated trading system. The goal is to create an explanatory financial-intelligence platform that can show how news, market data, and historical evaluation can be connected in a reproducible academic project.

## Architecture

FinSent is a Python/Dash application backed by SQLite. Provider routers fetch market data and news from Alpaca first for the US live demo, with optional Polygon, Kite, Marketaux, and web fallback paths. The dashboard view model builds a normalized state that feeds the Overview, Stock Research, News Intelligence, Compare, Alerts, and Research pages.

## Live Functionality

The live application can fetch Alpaca IEX quotes/bars, Alpaca/Benzinga current news, run FinBERT sentiment, classify catalysts, compute Signal V1 and Signal V2, add market/sector context, persist local rows, and show provider/runtime diagnostics.

## ML Component

FinBERT provides headline-level financial sentiment. Its output is used as an input to the explanatory signal layer. Model confidence is treated as model/engineering confidence, not as a probability of price movement.

## Catalyst Component

Catalyst Intelligence is deterministic. It classifies event type, direction, impact, horizon, novelty, recency, and event grouping from already-fetched news. It improves explainability but was not proven to improve predictive performance.

## Signal Component

Signal V1 is a compact deterministic news-plus-quote-quality signal. Signal V2 is componentized and combines news, price momentum, and volume confirmation, then attenuates reliability through liquidity, freshness, and data quality. Both are explanatory signals, not trading instructions.

## Evaluation

The locked Phase 16 final evaluation used bounded FNSPID/Yahoo historical research data at a 1D horizon. The final technical-eligible cohort had `N=111`, represented by AMZN, NVDA, and TSLA.

| Metric | Signal V1 | Signal V2.0 |
|---|---:|---:|
| Strict accuracy | 32.4% | 22.5% |
| Balanced accuracy | 51.9% | 39.2% |
| Directional accuracy | 50.0% | 54.3% |

Relevant baselines:

| Baseline | Strict accuracy |
|---|---:|
| Majority class | 55.0% |
| Always neutral | 6.3% |
| News direction | 31.5% |

## Findings

Signal V2.0 produced slightly higher directional accuracy on fewer directional predictions, but V1 performed better on strict and balanced accuracy. The majority-class baseline was strong because the realized final cohort was imbalanced. The result is academically useful because it shows that adding components does not automatically improve final-holdout performance.

## Limitations

- `N=111` final technical-eligible observations.
- Final represented symbols were AMZN, NVDA, and TSLA.
- 1D horizon only.
- FNSPID/Yahoo research data, not a universal market dataset.
- No profitability evaluation.
- No transaction costs or trading execution.
- No evidence of financial return advantage.
- Live Alpaca Basic/IEX is not consolidated SIP.

## Engineering Rigor

FinSent includes provider routing/fallbacks, local persistence, data-quality states, runtime diagnostics, cache hardening, stale-cache semantics, idempotent signal persistence, a locked final evaluation, and no-secret Git/data policies.
