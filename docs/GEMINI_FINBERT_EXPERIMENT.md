# Gemini vs FinBERT Experiment

Phase 9 adds a controlled framework for comparing Gemini and FinBERT on the same stored financial-news articles. It is a research framework, not a claim of final model superiority.

## Primary Questions

A. Model agreement:

```text
How often do Gemini and FinBERT produce the same normalized sentiment direction?
```

B. Realized directional alignment:

```text
For each article/model prediction, does the normalized direction agree with Event Study V2 realized return?
```

C. Horizon behavior:

- `1H`
- `4H`
- `1D`

D. Confidence relationship:

Confidence is described by bucketed outcomes only. Phase 9 does not calibrate confidence.

E. Catalyst analysis:

Gemini catalyst metadata may be used to group articles. FinBERT does not produce catalysts, so any catalyst grouping for FinBERT is explicitly based on Gemini's article-level metadata.

F. Disagreement analysis:

When Gemini and FinBERT disagree, the framework reports which model aligns with realized return, whether both are wrong, and whether the realized outcome is neutral.

## Paired Observation

The experiment unit is:

```text
one article
one instrument
one publication timestamp
same canonical SentimentAnalysisInput
Gemini result
FinBERT result
Event Study V2 result(s)
```

Different article samples are not compared as if they were paired.

## Eligibility

Required:

- valid publication timestamp
- identifiable instrument
- non-empty article text
- deduplicated article sample
- valid Gemini run or compatible reused Gemini run
- valid FinBERT run or compatible reused FinBERT run
- valid Event Study V2 result for the requested horizon

Exclusion reasons are explicit:

- `GEMINI_FAILED`
- `FINBERT_FAILED`
- `NO_MARKET_DATA`
- `INVALID_EVENT_STUDY`
- `UNSUPPORTED_HORIZON`
- `MISSING_TIMESTAMP`
- `DUPLICATE_SAMPLE`
- `DEPENDENCY_MISSING`
- `MISSING_INSTRUMENT`
- `MISSING_CONTENT`
- `SAMPLE_LIMIT`

## Selection

`ArticleSelectionService` selects stored articles by symbol, market, provider, date range, content availability, and deterministic sample limit. Duplicate control uses `dedupe_hash` first, then URL, then a title/ticker/time fallback key.

If eligible rows exceed the configured cap, seeded sampling is used and the final sample is returned in chronological order.

## Execution

`GeminiFinBertExperimentRunner`:

1. builds one canonical `SentimentAnalysisInput`
2. runs or reuses Gemini
3. runs or reuses FinBERT
4. evaluates Event Study V2 horizons
5. links outputs to an optional `ExperimentRun`
6. returns structured summaries and row-level observations

One model's output is never passed into the other model's input.

## Reuse

Existing runs may be reused when article text, model family/name/version, analysis method, normalization version, and prompt/config fingerprint match exactly. `force_rerun` disables reuse.

## Safety

Default limits are small. Dry-run mode makes zero Gemini calls, runs zero expensive FinBERT inference, writes no research rows, and reports dependency/credential readiness plus Event Study V2 coverage.

No heuristic output is labeled as Gemini in the comparison framework.
