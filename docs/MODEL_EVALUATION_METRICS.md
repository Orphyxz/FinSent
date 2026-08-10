# Model Evaluation Metrics

Phase 9 metrics are descriptive and must always be read with sample size `N`.

## Direction Normalization

Model score direction uses:

```text
score > 0.15  => BULLISH
score < -0.15 => BEARISH
otherwise     => NEUTRAL
```

Version: `direction_v1_score_0_15_return_0_001`.

## Realized Direction

Event Study V2 raw returns use a neutral band:

```text
return > 0.001  => BULLISH
return < -0.001 => BEARISH
otherwise       => NEUTRAL
```

This avoids treating tiny market noise as a directional outcome.

## Agreement

Gemini-vs-FinBERT agreement is exact directional agreement:

```text
Gemini BULLISH + FinBERT BULLISH = agreement
Gemini BULLISH + FinBERT BEARISH = disagreement
```

The framework also builds a three-class agreement matrix.

## Accuracy

Strict three-class accuracy:

```text
prediction == realized_direction
```

Directional accuracy excludes neutral predictions and neutral outcomes. Neutral samples are counted and reported, not silently removed.

## Precision, Recall, F1

Metrics are calculated for:

- `BULLISH`
- `NEUTRAL`
- `BEARISH`

Zero-division cases return null rather than false precision.

## Balanced Accuracy

Balanced accuracy is the mean of available class recalls. It is useful because financial-news samples may be class-imbalanced.

## Confidence Buckets

Confidence is analyzed separately for each model. Buckets are:

- `0.0-0.5`
- `0.5-0.6`
- `0.6-0.7`
- `0.7-0.8`
- `0.8-0.9`
- `0.9-1.0`

Gemini confidence and FinBERT confidence have different semantics and are not treated as directly interchangeable.

## Horizon-Specific Evaluation

Metrics are calculated separately for `1H`, `4H`, and `1D`. Phase 9 does not mix horizons into one undifferentiated accuracy number.

## Disagreement Analysis

For rows where Gemini and FinBERT directions differ, the framework reports:

- sample count
- Gemini correct
- FinBERT correct
- both wrong
- realized neutral

## Confidence Intervals

Directional/strict accuracy can include Wilson intervals for proportions. Intervals are descriptive uncertainty estimates, not proof of statistical significance.

## Significance Testing

McNemar-style paired significance testing is not enabled in Phase 9 because small local smoke datasets generally do not satisfy useful sample-size assumptions. The framework reports insufficient evidence rather than forcing p-values.

## Limitations

- No metric proves profitability.
- No metric is meaningful without `N`.
- Tiny samples are smoke validation only.
- Event Study V2 returns are outcome measurements, not model inputs.
