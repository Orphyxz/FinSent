# Confidence Semantics

Phase 2 freezes what current confidence values mean. These values are not calibrated probabilities and must not be presented as the chance that a stock will rise or fall.

## Article Model Confidence

- Source: `ArticleAnalysis.confidence` from the configured live analyzer, normally `FinBERTNewsAnalyzer`, or a heuristic fallback. Phase 6's canonical `SentimentAnalysisResult.confidence` stores analyzer-specific confidence for research runs.
- Stored as: `news_articles.model_confidence`.
- Range: `0.0` to `1.0`.
- Interpretation: analyzer self-assessed confidence in the per-article sentiment/impact classification.
- Not: a probability of future price direction, a backtested accuracy score, or a market-implied probability.

Analyzer-specific semantics:

- Gemini: model/self-assessed structured output confidence.
- FinBERT: winning classifier class probability.
- Heuristic: rule-derived internal score.

These values are not calibrated against each other in Phase 6.

## Article Signal Confidence

- Source: `SentimentResult.signal_confidence` during repository persistence.
- Stored as: `news_articles.signal_confidence`.
- Range: `0.0` to `1.0`.
- Current behavior: mirrors article model confidence in the active pipeline.
- Not: a separately calibrated signal-confidence model.

## Aggregate Confidence

- Source: the configured live analyzer's `aggregate` method, normally `FinBERTNewsAnalyzer.aggregate`.
- Stored as: `signal_snapshots.overall_confidence`.
- Range: `0.0` to `1.0`.
- Current behavior: average article confidence across analyzed article pairs.
- Not: a portfolio-level or ticker-level predictive confidence.

## Signal Confidence

- Source: `CompositeSignalEngine.compute`.
- Stored as: `signal_snapshots.signal_confidence`.
- Range: `0.0` to `1.0`.
- Current behavior: aggregate confidence minus the quote freshness penalty when a usable stale/delayed quote exists. It is `0.0` when there are no article pairs.
- Not: a forecast probability, expected return confidence interval, or calibrated trading edge.

## Signal V2 Confidence

- Source: `SignalEngineV2.evaluate`.
- Stored as: `signal_runs.confidence` for live and explicit V2 executions.
- Range: `0.0` to `1.0`.
- Current behavior: engineering reliability score derived from final score magnitude, component reliability, component agreement, and directional component availability.
- Not: a calibrated probability, a backtested hit rate, or a trading recommendation confidence.

V2 confidence labels are:

- `high`: `>= 0.70`
- `medium`: `>= 0.40`
- `low`: otherwise

V2 confidence is intentionally separate from article model confidence. It can decrease when data is stale, low-quality, internally conflicting, or missing, even if one directional component is strong.

## Dashboard Confidence Labels

- `Signal Confidence` in metrics is the active signal/article confidence described above.
- `Average Confidence` in news-impact views is average article/model confidence.
- Compare-page confidence ranks model confidence, not future accuracy.

## Future Calibration Work

- Continue using experiment tables for model outputs and realized future returns.
- Evaluate any future confidence calibration by horizon and exchange without touching locked final holdout data.
- Separate article classification confidence from signal reliability.
- Display calibrated probabilities only after backtested calibration exists.
- Use `sentiment_analysis_runs` to compare model confidence behavior only in a later dedicated calibration phase.
- Calibrate `signal_runs` confidence only after strict event-study/backtest data exists.

## Phase 14 Calibration

Calibrated reliability is an optional empirical correctness estimate fitted on Phase 12 DEVELOPMENT only. It is not probability of price increase or profit, and it does not change signal direction.
