# Signal Components V2

Each V2 component returns:

- name
- availability
- raw value
- normalized value
- weight
- contribution
- reliability
- reason
- metadata

## News

For each article:

```text
article_weight = relevance * confidence * impact_strength * recency_weight * provenance_factor
direction = +1 bullish, -1 bearish, 0 neutral
```

The component score is:

```text
news_score = sum(direction * article_weight) / sum(article_weight)
```

Recency uses a simple 72-hour linear decay:

```text
recency_weight = max(0.20, 1 - age_hours / 72 * 0.80)
```

Heuristic fallback articles use `provenance_factor = 0.75`.

Disagreement is:

```text
agreement = abs(sum(direction * article_weight)) / sum(article_weight)
```

It affects reliability/confidence, not arbitrary direction.

Example:

```text
2 strong bullish articles, no bearish:
agreement close to 1.0, positive score

1 bullish and 1 bearish with similar weights:
agreement close to 0.0, score near neutral
```

## Price Momentum

Momentum uses close-to-close returns over available recent bar horizons:

- 1 bar
- up to 4 bars
- up to 16 bars

Horizon priors:

```text
1 bar: 0.50
4 bars: 0.30
16 bars: 0.20
```

Each return is normalized:

```text
normalized_return = clamp(raw_return / 0.05, -1, 1)
```

The component score is the weighted average of available normalized returns.

Example:

```text
last close = 105
close 4 bars ago = 100
raw return = 0.05
normalized = 1.0
```

## Volume Confirmation

Volume is confirmation, not independent direction.

```text
relative_volume = recent_volume / median(previous up to 20 volumes)
confirmation = clamp((relative_volume - 1) / 2, -0.5, 0.5)
volume_score = sign(existing_direction) * abs(confirmation)
```

If there is no existing direction from news or momentum, volume score is `0`.

Examples:

```text
positive momentum + relative volume 3.0 => positive confirmation
positive momentum + relative volume 0.3 => weak/negative confirmation
flat price + high volume => no direction
```

## Phase 13 Tuning Boundary

Phase 13 recombines cached V2 component values from the Phase 12 DEVELOPMENT rows only. It does not change how news, price momentum, volume, liquidity, freshness, or data-quality components are computed.

Allowed research-only tuning:

- news directional weight
- price-momentum directional weight
- volume-confirmation directional weight
- symmetric bullish/bearish threshold

Frozen:

- component formulas
- FinBERT inputs and outputs
- news decay
- momentum normalization
- volume confirmation semantics
- confidence formula
- strong-label threshold

## Liquidity

Liquidity uses bid/ask spread percentage where available:

```text
spread_pct = spread / midpoint
reliability = 1 - min(spread_pct / 0.01, 1) * 0.45
```

Missing bid/ask or spread reduces confidence but does not create bearish direction.

## Freshness

Freshness uses Phase 4 labels:

| Freshness | Reliability |
|---|---:|
| `FRESH` | 1.00 |
| `AGING` | 0.78 |
| `STALE` | 0.45 |
| `UNKNOWN` | 0.60 |

Freshness attenuates trust, not market direction.

## Data Quality

Data quality uses supplied `DataQualityAssessment.score`.

If several assessments are supplied, V2 averages them. The result attenuates score magnitude and confidence without changing direction.

## Missing Inputs

Unavailable directional components are excluded from directional-weight normalization. Missing reliability inputs use conservative reliability defaults and create warnings where useful.
