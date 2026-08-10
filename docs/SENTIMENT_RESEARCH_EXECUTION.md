# Sentiment Research Execution

Phase 6 adds the plumbing for reproducible model runs. It does not execute large comparisons or calculate accuracy metrics.

## Create An Experiment

Use `ExperimentRepository` to create a row in `experiment_runs`, then pass its id to sentiment execution.

```python
experiment = ExperimentRepository(session).create(
    name="gemini-vs-finbert-smoke",
    experiment_type="MODEL_COMPARISON",
    configuration={"limit": 5},
)
```

## Run One Analyzer

Use `SentimentIntelligenceService` with a canonical `SentimentAnalysisInput`.

```python
service = SentimentIntelligenceService(session=session)
record = service.analyze(
    analysis_input,
    analyzer_name="heuristic",
    experiment_id=experiment.id,
)
```

## Run A Small Batch

The batch API is deterministic, sequential, limit-bounded, and tolerant of per-item failures.

```python
summary = service.analyze_articles(
    inputs,
    analyzer_name="finbert",
    experiment_id=experiment.id,
    limit=10,
)
```

## CLI

The safe CLI runs over already-stored articles only:

```powershell
python -m finsent.scripts.run_sentiment_analysis --symbol AAPL --analyzer heuristic --limit 3
```

Useful options:

- `--article-id`
- `--analyzer gemini|finbert|heuristic`
- `--experiment-id`
- `--limit`
- `--no-persist`

The command does not scrape providers, process the CSV archive, or run a full comparison.

## Later Comparison

Phase 9 adds the first controlled Gemini-vs-FinBERT comparison framework. It uses the same canonical article input for both analyzers, can reuse exact compatible stored runs, links results to Event Study V2 outcomes, and exports row-level/summary research artifacts. It remains descriptive and does not calibrate confidence or optimize Signal V2.
