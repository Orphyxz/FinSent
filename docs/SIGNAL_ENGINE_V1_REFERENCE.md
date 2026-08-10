# Signal Engine V1 Reference

Phase 2 freezes the current `CompositeSignalEngine` behavior before any Signal Engine V2 work.

## Inputs

- Quote snapshot from Polygon/Kite/unavailable provider.
- Normalized article plus article analysis pairs.
- Aggregate analysis from Gemini analyzer or heuristic fallback.

## Usable Market Quote Criteria

A quote only counts as usable market data when all are true:

- `current_price` exists and is greater than zero.
- `market_timestamp` exists.
- `quality_status` is `live`, `delayed`, or `stale`.
- provider status is not `UNCONFIGURED` or `UNAVAILABLE`.

Unavailable quote objects no longer create market/quote modes or penalties by object existence alone.

## News Score

For each article:

- `recency_weight = max(0.2, 1.0 - min(age_hours / 72.0, 0.8))`
- direction is `1.0` for bullish, `-1.0` for bearish, and `0.0` for neutral.
- article weight is `recency_weight * confidence * impact_strength`.

If total article weight is positive:

- `news_score = sum(direction * weight) / sum(weight)`

If there are no article pairs:

- `news_score = 0.0`

## Quote Quality Adjustments

Only usable quotes affect these terms.

- `liquidity_penalty = min(spread_percentage / 0.01, 1.0)` when spread exists.
- `freshness_penalty = min((freshness_seconds - 300) / 1800.0, 1.0)` when quote age exceeds 300 seconds.
- `market_component = 0.1` only for usable `live` quotes.
- `market_component = 0.0` for delayed or stale usable quotes.

## Composite Score

`composite_score = clamp((0.75 * news_score) + (0.25 * market_component) - (0.10 * liquidity_penalty) - (0.10 * freshness_penalty), -1.0, 1.0)`

## Labels

- `bullish` when score is strictly greater than `0.18`.
- `bearish` when score is strictly less than `-0.18`.
- `neutral` otherwise.

## Modes

- `News + Quote Quality`: usable quote and article pairs exist.
- `Quote-quality fallback`: usable quote exists but no article pairs exist.
- `News-only signal`: article pairs exist but usable quote does not.
- `Unavailable`: neither usable quote nor article pairs exist.

## Confidence

- `signal_confidence = clamp(aggregate.overall_confidence - (0.1 * freshness_penalty), 0.0, 1.0)`
- If there are no article pairs, aggregate confidence is treated as `0.0`.

This confidence is not a calibrated probability of future price direction.

## Known Weaknesses

- No price momentum, volume momentum, RSI, MACD, or technical-indicator scoring.
- No order-flow or true buy/sell pressure model.
- The market component is a small quote-quality/live-data adjustment.
- No backtested calibration of confidence or thresholds.
- Event-study output still uses the Phase 1 loose matcher.

## Claims That Must Not Be Made About V1

- Do not claim V1 performs sophisticated technical analysis.
- Do not claim V1 estimates buying/selling pressure.
- Do not claim V1 estimates the probability that a stock will rise.
- Do not call the mode `Market + News`; it is a news signal with quote-quality adjustment.
